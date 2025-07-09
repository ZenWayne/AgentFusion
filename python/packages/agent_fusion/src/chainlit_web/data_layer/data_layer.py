from chainlit.data.chainlit_data_layer import ChainlitDataLayer

class AgentFusionDataLayer(ChainlitDataLayer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def get_user(self, identifier: str):
        return await super().get_user(identifier)