from src.infrastructure.provider_factory.connection_models import ConnectionModelNaturalLanguage


class ConnectAWSBedrock(ConnectionModelNaturalLanguage):
    def connection(self):
        from botocore.config import Config
        from langchain_aws import ChatBedrockConverse

        return ChatBedrockConverse(model_id=self.model, region_name=self.settings.AWS_REGION,
                                   temperature=0, max_tokens=self.settings.OUTPUT_TOKEN_BUDGET,
                                   config=Config(connect_timeout=self.settings.LLM_TIMEOUT,
                                                 read_timeout=self.settings.LLM_TIMEOUT,
                                                 retries={"total_max_attempts": 1}))
