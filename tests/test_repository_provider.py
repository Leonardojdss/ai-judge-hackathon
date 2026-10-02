import base64
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

from github import GithubException
from requests.exceptions import Timeout
import pytest

from src.infrastructure.repository.provider import RepositoryProvider
from src.utils.errors import AssessmentError


@pytest.fixture
def sdk(settings, monkeypatch):
    settings.GITHUB_APP_ID = "123"
    from pydantic import SecretStr
    settings.GITHUB_APP_PRIVATE_KEY = SecretStr("not-a-real-key")
    integration = MagicMock()
    integration.get_repo_installation.return_value = NS(id=789)
    integration.get_access_token.return_value = NS(token="private-token")
    repo = MagicMock()
    repo.default_branch = "main"
    repo.private = False
    repo.get_commit.return_value = NS(sha="a" * 40, commit=NS(tree=NS(sha="tree-sha")))
    repo.get_git_tree.return_value = NS(truncated=False, tree=[NS(path="README.md", size=10, mode="100644", type="blob"), NS(path="src/main.py", size=10, mode="100644", type="blob")])
    repo.get_contents.return_value = NS(size=10, decoded_content=b"print(42)\n")
    github = MagicMock()
    github.get_repo.return_value = repo
    app_auth = MagicMock()
    github_constructor = MagicMock(return_value=github)
    monkeypatch.setattr("src.infrastructure.repository.provider.Auth.AppAuth", app_auth)
    monkeypatch.setattr("src.infrastructure.repository.provider.GithubIntegration", MagicMock(return_value=integration))
    monkeypatch.setattr("src.infrastructure.repository.provider.Github", github_constructor)
    provider = RepositoryProvider("https://github.com/owner/repo", "feature", settings)
    return provider, repo, integration, github_constructor


def test_selects_repo_installation_and_pins_all_reads(sdk):
    provider, repo, integration, constructor = sdk
    metadata = provider.get_repository_metadata()
    integration.get_repo_installation.assert_called_once_with("owner", "repo")
    integration.get_access_token.assert_called_once_with(789)
    assert "retry" not in constructor.call_args.kwargs
    assert "timeout" not in constructor.call_args.kwargs
    repo.get_commit.assert_called_once_with("feature")
    assert metadata["commit"] == "a" * 40
    assert provider.tools["read_file"].invoke({"formatted_filepath": "src/main.py"}) == "print(42)\n"
    repo.get_contents.assert_called_once_with("src/main.py", ref="a" * 40)
    assert provider.get_readme() == ("README.md", "print(42)\n")
    assert set(provider.tools) == {"read_file", "list_files_in_main_branch", "list_files_in_bot_branch", "get_files_from_directory"}
    with pytest.raises(AssessmentError, match="não permitida"):
        provider.tools["read_file"].api_wrapper.run("create_file", "bad")


@pytest.mark.parametrize("status,code", [(401, "REPOSITORY_AUTH"), (403, "REPOSITORY_AUTH")])
def test_auth_and_missing_repo_do_not_retry(sdk, status, code):
    provider, repo, integration, _ = sdk
    integration.get_repo_installation.side_effect = GithubException(status, {"message": "secret must not leak"}, {})
    with pytest.raises(AssessmentError) as caught:
        provider.connect()
    assert caught.value.code == code
    assert "secret" not in str(caught.value)
    assert integration.get_repo_installation.call_count == 1


def test_missing_installation_falls_back_to_public_read_only_access(sdk):
    provider, repo, integration, constructor = sdk
    integration.get_repo_installation.side_effect = GithubException(404, {}, {})

    metadata = provider.get_repository_metadata()

    assert metadata["commit"] == "a" * 40
    assert provider.access_mode == "public_unauthenticated"
    assert constructor.call_count == 1
    assert constructor.call_args.kwargs == {}
    repo.get_commit.assert_called_once_with("feature")


def test_public_fallback_preserves_not_found_for_missing_repository(sdk):
    provider, _, integration, constructor = sdk
    integration.get_repo_installation.side_effect = GithubException(404, {}, {})
    public_client = MagicMock()
    public_client.get_repo.side_effect = GithubException(404, {}, {})
    constructor.side_effect = [public_client]

    with pytest.raises(AssessmentError) as caught:
        provider.connect()

    assert caught.value.code == "NOT_FOUND"


def test_public_fallback_rejects_private_repository_without_installation(sdk):
    provider, repo, integration, _ = sdk
    integration.get_repo_installation.side_effect = GithubException(404, {}, {})
    repo.private = True

    with pytest.raises(AssessmentError) as caught:
        provider.connect()

    assert caught.value.code == "REPOSITORY_AUTH"


def test_public_repository_does_not_require_github_app_credentials(settings, monkeypatch):
    repo = NS(
        private=False,
        default_branch="main",
        get_commit=lambda ref: NS(sha="a" * 40, commit=NS(tree=NS(sha="tree-sha"))),
    )
    github = MagicMock()
    github.get_repo.return_value = repo
    constructor = MagicMock(return_value=github)
    monkeypatch.setattr("src.infrastructure.repository.provider.Github", constructor)
    provider = RepositoryProvider("https://github.com/owner/repo", None, settings)

    assert provider.get_repository_metadata()["commit"] == "a" * 40
    assert provider.access_mode == "public_unauthenticated"
    constructor.assert_called_once_with()


def test_public_token_authenticates_public_fallback(settings, monkeypatch):
    from pydantic import SecretStr

    settings.GITHUB_PUBLIC_TOKEN = SecretStr("public-token")
    repo = NS(
        private=False,
        default_branch="main",
        get_commit=lambda ref: NS(sha="a" * 40, commit=NS(tree=NS(sha="tree-sha"))),
    )
    github = MagicMock()
    github.get_repo.return_value = repo
    constructor = MagicMock(return_value=github)
    token_auth = MagicMock()
    monkeypatch.setattr("src.infrastructure.repository.provider.Auth.Token", token_auth)
    monkeypatch.setattr("src.infrastructure.repository.provider.Github", constructor)
    provider = RepositoryProvider("https://github.com/owner/repo", None, settings)

    provider.connect()

    token_auth.assert_called_once_with("public-token")
    constructor.assert_called_once_with(auth=token_auth.return_value)
    assert provider.access_mode == "public_token"


def test_partial_github_app_configuration_is_rejected(settings):
    settings.GITHUB_APP_ID = "123"
    provider = RepositoryProvider("https://github.com/owner/repo", None, settings)

    with pytest.raises(AssessmentError) as caught:
        provider.connect()

    assert caught.value.code == "CONFIGURATION_ERROR"


@pytest.mark.parametrize("error", [GithubException(429, {}, {}), GithubException(503, {}, {}), GithubException(403, {}, {"x-ratelimit-remaining": "0"}), Timeout()])
def test_transient_errors_are_translated_without_application_retry(sdk, error):
    provider, repo, integration, _ = sdk
    integration.get_repo_installation.side_effect = error
    with pytest.raises(AssessmentError):
        provider.connect()
    assert integration.get_repo_installation.call_count == 1


def test_missing_file_not_treated_as_content(sdk):
    provider, repo, *_ = sdk
    provider.connect()
    with pytest.raises(AssessmentError) as caught:
        provider.read_file("absent.py")
    assert caught.value.code == "NOT_FOUND"
    repo.get_contents.assert_not_called()


def test_truncated_tree_is_walked_by_tree_sha(sdk):
    provider, repo, *_ = sdk
    repo.get_git_tree.side_effect = [NS(truncated=True, tree=[]),
        NS(truncated=False, tree=[NS(path="src", type="tree", sha="subtree")]),
        NS(truncated=False, tree=[NS(path="main.py", type="blob", mode="100644", size=10)])]
    assert provider.get_file_tree() == [{"path": "src/main.py", "size": 10, "mode": "100644"}]
    assert not provider.tree_truncated
    assert repo.get_git_tree.call_args_list[1].args == ("tree-sha",)
    assert repo.get_git_tree.call_args_list[2].args == ("subtree",)


def test_no_readme_is_valid(sdk):
    provider, repo, *_ = sdk
    repo.get_git_tree.return_value = NS(truncated=False, tree=[])
    assert provider.get_readme() == (None, None)


def test_binary_and_symlink_rejected(sdk):
    provider, repo, *_ = sdk
    provider.connect()
    repo.get_contents.return_value = NS(size=4, decoded_content=b"\x00bad")
    with pytest.raises(AssessmentError) as caught:
        provider.read_file("src/main.py")
    assert caught.value.code == "BINARY_FILE"
    provider._tree = [{"path": "link.py", "mode": "120000", "size": 4}]
    with pytest.raises(AssessmentError) as caught:
        provider.read_file("link.py")
    assert caught.value.code == "FILE_EXCLUDED"


def test_large_file_with_omitted_contents_uses_pinned_git_blob(sdk):
    provider, repo, *_ = sdk
    provider.connect()
    repo.get_contents.return_value = NS(encoding="none", sha="large-blob-sha")
    repo.get_git_blob.return_value = NS(
        encoding="base64",
        content=base64.b64encode("id,description\n1,conteúdo\n".encode()).decode(),
    )

    assert provider.read_file("src/main.py") == "id,description\n1,conteúdo\n"
    repo.get_contents.assert_called_once_with("src/main.py", ref="a" * 40)
    repo.get_git_blob.assert_called_once_with("large-blob-sha")


def test_real_sdk_constructors_use_their_native_defaults(settings, monkeypatch):
    """Keep SDK constructors real; mock only calls that would reach GitHub."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from github import Github, GithubIntegration
    from pydantic import SecretStr

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings.GITHUB_APP_ID = "123"
    settings.GITHUB_APP_PRIVATE_KEY = SecretStr(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode())
    repo = NS(default_branch="main", get_commit=lambda ref: NS(
        sha="a" * 40, commit=NS(tree=NS(sha="tree-sha"))))
    monkeypatch.setattr(GithubIntegration, "get_repo_installation", lambda self, owner, name: NS(id=789))
    monkeypatch.setattr(GithubIntegration, "get_access_token", lambda self, installation_id: NS(token="test-token"))
    monkeypatch.setattr(Github, "get_repo", lambda self, name: repo)
    provider = RepositoryProvider("https://github.com/owner/repo", None, settings)
    try:
        assert provider.get_repository_metadata()["commit"] == "a" * 40
        assert isinstance(provider._integration, GithubIntegration)
        assert isinstance(provider._github, Github)
    finally:
        provider.close()

def test_sdk_configuration_error_is_not_reported_as_invalid_credentials(sdk, monkeypatch):
    provider, *_ = sdk
    monkeypatch.setattr("src.infrastructure.repository.provider.GithubIntegration", MagicMock(side_effect=AssertionError()))
    with pytest.raises(AssessmentError) as caught:
        provider.connect()
    assert caught.value.code == "GITHUB_CLIENT_CONFIGURATION"
