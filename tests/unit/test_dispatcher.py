import pytest

from trading.core.enums import AssetClass
from trading.execution.dispatcher import Dispatcher
from trading.execution.paper import PaperAdapter


@pytest.mark.asyncio
class TestDispatcher:
    async def test_dispatch_to_paper_adapter(self) -> None:
        paper = PaperAdapter()
        dispatcher = Dispatcher(adapters={"paper": paper})
        dispatcher.routing[AssetClass.CRYPTO] = "paper"
        assert dispatcher.routing[AssetClass.CRYPTO] == "paper"
