from src.infrastructure.provider_factory.connection_models import ConnectionModelNaturalLanguage


class ConnectAWSBedrock(ConnectionModelNaturalLanguage):
    def connection(self):
        from langchain_aws import ChatBedrockConverse

        return ChatBedrockConverse(model_id=self.model, region_name=self.settings.AWS_REGION,
                                   temperature=0)
