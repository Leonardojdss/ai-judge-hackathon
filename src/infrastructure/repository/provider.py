import json
from pathlib import PurePosixPath

from github import Auth, Github, GithubException, GithubIntegration
from langchain_community.agent_toolkits.github.toolkit import GitHubToolkit
from langchain_community.utilities.github import GitHubAPIWrapper
from pydantic import PrivateAttr
from requests.exceptions import ConnectionError, Timeout

from src.config.settings import Settings
from src.utils.errors import AssessmentError


class ReadOnlyGitHubWrapper(GitHubAPIWrapper):
    """Keep the notebook toolkit API, with typed failures and a fixed commit.

    Authentication is initialized by the provider, not the upstream validator
    (which picks the first installation). Only these modes can be executed.
    """

    _provider = PrivateAttr()

    def run(self, mode: str, query: str) -> str:
        if mode == "read_file":
            return self._provider.read_file(query)
        if mode in {"list_files_in_main_branch", "list_files_in_bot_branch"}:
            return json.dumps([f["path"] for f in self._provider.get_file_tree()])
        if mode == "get_files_from_directory":
            prefix = query.strip("/")
            return json.dumps([f["path"] for f in self._provider.get_file_tree()
                               if not prefix or f["path"].startswith(prefix + "/")])
        raise AssessmentError("TOOL_FORBIDDEN", "Operação de ferramenta não permitida.", 403)


def translate_github_error(exc: Exception) -> AssessmentError:
    if isinstance(exc, AssessmentError):
        return exc
    if isinstance(exc, (Timeout, TimeoutError)):
        return AssessmentError("REPOSITORY_TIMEOUT", "Tempo limite de acesso ao GitHub.", 504)
    if isinstance(exc, ConnectionError):
        return AssessmentError("REPOSITORY_UNAVAILABLE", "GitHub temporariamente indisponível.", 502)
    if isinstance(exc, GithubException):
        status = exc.status
        headers = exc.headers or {}
        rate_limited = status == 429 or (status == 403 and (
            headers.get("x-ratelimit-remaining") == "0" or "retry-after" in headers))
        if rate_limited:
            return AssessmentError("RATE_LIMIT", "Limite de requisições do GitHub atingido.", 502)
        if status in (401, 403):
            return AssessmentError("REPOSITORY_AUTH", "Acesso ao repositório não autorizado.", 403)
        if status == 404:
            return AssessmentError("NOT_FOUND", "Repositório, referência ou arquivo não encontrado.", 404)
        if status in (500, 502, 503, 504):
            return AssessmentError("REPOSITORY_UNAVAILABLE", "GitHub temporariamente indisponível.", 502)
    return AssessmentError("REPOSITORY_ERROR", "Falha ao consultar o repositório.")


class RepositoryProvider:
    def __init__(self, repository_url: str, ref: str | None, settings: Settings):
        self.name = repository_url.removeprefix("https://github.com/")
        self.url = repository_url
        self.ref = ref
        self.settings = settings
        self._repo = None
        self._github = None
        self._integration = None
        self._tree = None
        self._cache: dict[str, str] = {}
        self.tree_truncated = False
        self.commit_sha = ""
        self.tree_sha = ""
        self.tools = {}

    def _call(self, operation):
        try:
            return operation()
        except Exception as exc:
            raise translate_github_error(exc) from None

    def connect(self):
        if self._repo is not None:
            return
        s = self.settings
        if not s.GITHUB_APP_ID or not (s.GITHUB_APP_PRIVATE_KEY or s.GITHUB_APP_PRIVATE_KEY_PATH):
            raise AssessmentError("CONFIGURATION_ERROR", "Configure as credenciais do GitHub App.", 500)
        try:
            key = (s.GITHUB_APP_PRIVATE_KEY.get_secret_value() if s.GITHUB_APP_PRIVATE_KEY
                   else s.GITHUB_APP_PRIVATE_KEY_PATH.read_text())
            auth = Auth.AppAuth(s.GITHUB_APP_ID, key)
            self._integration = GithubIntegration(auth=auth)
            owner, repo_name = self.name.split("/")
            installation = self._call(lambda: self._integration.get_repo_installation(owner, repo_name))
            token = self._call(lambda: self._integration.get_access_token(installation.id))
            self._github = Github(auth=Auth.Token(token.token))
            self._repo = self._call(lambda: self._github.get_repo(self.name))
        except AssessmentError:
            raise
        except (AssertionError, TypeError):
            raise AssessmentError("GITHUB_CLIENT_CONFIGURATION", "Falha ao configurar o cliente GitHub.", 500) from None
        except Exception:
            raise AssessmentError("CONFIGURATION_ERROR", "Credenciais do GitHub App inválidas.", 500) from None
        commit = self._call(lambda: self._repo.get_commit(self.ref or self._repo.default_branch))
        self.commit_sha = commit.sha
        self.tree_sha = commit.commit.tree.sha
        # model_construct deliberately bypasses upstream authentication: the exact
        # installation has already been selected for the requested repository.
        wrapper = ReadOnlyGitHubWrapper.model_construct(
            github=self._github, github_repo_instance=self._repo, github_repository=self.name,
            github_app_id=s.GITHUB_APP_ID, github_app_private_key="",
            active_branch=self.commit_sha, github_base_branch=self.commit_sha)
        wrapper._provider = self
        toolkit = GitHubToolkit.from_github_api_wrapper(wrapper)
        allowed = {"read_file", "list_files_in_main_branch", "list_files_in_bot_branch", "get_files_from_directory"}
        self.tools = {t.mode: t for t in toolkit.get_tools() if t.mode in allowed}

    def get_repository_metadata(self) -> dict:
        self.connect()
        return {"name": self.name, "url": self.url, "commit": self.commit_sha,
                "requested_ref": self.ref, "default_branch": self._repo.default_branch}

    def get_file_tree(self) -> list[dict]:
        if self._tree is not None:
            return self._tree
        self.connect()
        root = self._call(lambda: self._repo.get_git_tree(self.tree_sha, recursive=True))
        entries = []
        if not root.truncated:
            entries = [{"path": e.path, "size": e.size or 0, "mode": e.mode}
                       for e in root.tree if e.type == "blob"]
        else:
            queue = [("", self.tree_sha)]
            while queue:
                prefix, sha = queue.pop(0)
                tree = self._call(lambda: self._repo.get_git_tree(sha))
                self.tree_truncated |= tree.truncated
                for entry in tree.tree:
                    path = prefix + entry.path
                    if entry.type == "tree":
                        queue.append((path + "/", entry.sha))
                    elif entry.type == "blob":
                        entries.append({"path": path, "size": entry.size or 0, "mode": entry.mode})
        self._tree = sorted(entries, key=lambda e: e["path"])
        return self._tree

    def read_file(self, path: str) -> str:
        from src.workflow_agentic.tools.repository_tools import exclusion_reason

        if path.startswith("/") or ".." in PurePosixPath(path).parts or exclusion_reason(path):
            raise AssessmentError("FILE_EXCLUDED", "Arquivo excluído da análise.", 422)
        if path in self._cache:
            return self._cache[path]
        entry = next((e for e in self.get_file_tree() if e["path"] == path), None)
        if entry is None:
            raise AssessmentError("NOT_FOUND", "Arquivo não encontrado no commit.", 404)
        if entry["mode"] == "120000":
            raise AssessmentError("FILE_EXCLUDED", "Links simbólicos não são analisados.", 422)
        content = self._call(lambda: self._repo.get_contents(path, ref=self.commit_sha))
        if isinstance(content, list):
            raise AssessmentError("NOT_A_FILE", "O caminho informado não representa um arquivo.", 422)
        raw = content.decoded_content
        try:
            text = raw.decode("utf-8")
            if "\0" in text:
                raise UnicodeError()
        except UnicodeError:
            raise AssessmentError("BINARY_FILE", "Conteúdo não textual excluído.", 422) from None
        self._cache[path] = text
        return text

    def get_readme(self) -> tuple[str | None, str | None]:
        choices = [e["path"] for e in self.get_file_tree()
                   if PurePosixPath(e["path"]).name.lower() in {"readme", "readme.md", "readme.rst", "readme.txt"}]
        if not choices:
            return None, None
        path = min(choices, key=lambda p: (p.count("/"), p.lower()))
        return path, self.read_file(path)

    def read_files(self, paths: list[str]) -> dict[str, str]:
        return {p: self.read_file(p) for p in paths}

    def close(self):
        for client in (self._github, self._integration):
            if client is not None:
                client.close()
