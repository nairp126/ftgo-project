import pytest
import asyncio
from app.services.ensembler import ModelEnsembler, EnsemblerError
from app.services.router import RoutingEngine, RoutingDecision
from app.schemas.chat import ChatRequest, ChatResponse, Message, Usage, Choice


class DummyRoutingEngine(RoutingEngine):
    """Mock router to simulate heterogeneous model latency and responses."""
    
    async def route_request(self, request, request_id: str):
        # Simulate different speeds and lengths based on the requested model
        if request.model == "model-fast":
            await asyncio.sleep(0.01)
            resp = ChatResponse(
                id="req-fast", created=123, model="model-fast",
                choices=[Choice(message=Message(role="assistant", content="Short"))],
                usage=Usage(completion_tokens=5)
            )
            decision = RoutingDecision(provider="dummy", request_id=request_id, original_model="model-fast", resolved_model="model-fast", reason="dummy")
            return resp, decision
            
        elif request.model == "model-slow":
            await asyncio.sleep(0.1)
            resp = ChatResponse(
                id="req-slow", created=123, model="model-slow",
                choices=[Choice(message=Message(role="assistant", content="Very long detailed response here"))],
                usage=Usage(completion_tokens=100)
            )
            decision = RoutingDecision(provider="dummy", request_id=request_id, original_model="model-slow", resolved_model="model-slow", reason="dummy")
            return resp, decision
            
        elif request.model == "model-fail":
            await asyncio.sleep(0.05)
            raise Exception("Provider overload")
            
        return None, None


@pytest.mark.asyncio
async def test_ensembler_fastest_strategy():
    router = DummyRoutingEngine()
    ensembler = ModelEnsembler(router)
    
    req = ChatRequest(
        model="default",
        messages=[Message(role="user", content="Hello")]
    )
    
    # model-fast resolves in 10ms, model-slow in 100ms
    response, decision = await ensembler.execute_ensemble(
        base_request=req,
        request_id="test-1",
        strategy="fastest",
        models=["model-slow", "model-fast"]
    )
    
    # We expect 'model-fast' despite being passed second
    assert decision.resolved_model == "model-fast"
    assert response.usage.completion_tokens == 5


@pytest.mark.asyncio
async def test_ensembler_longest_strategy():
    router = DummyRoutingEngine()
    ensembler = ModelEnsembler(router)
    
    req = ChatRequest(
        model="default",
        messages=[Message(role="user", content="Hello")]
    )
    
    # longest strategy should wait for the slow model to finish and return its result since it has more tokens
    response, decision = await ensembler.execute_ensemble(
        base_request=req,
        request_id="test-2",
        strategy="longest",
        models=["model-slow", "model-fast"]
    )
    
    assert decision.resolved_model == "model-slow"
    assert response.usage.completion_tokens == 100


@pytest.mark.asyncio
async def test_ensembler_partial_failure():
    router = DummyRoutingEngine()
    ensembler = ModelEnsembler(router)
    
    req = ChatRequest(
        model="default",
        messages=[Message(role="user", content="Hello")]
    )
    
    # If one model fails, the ensemble should still succeed with the surviving model
    response, decision = await ensembler.execute_ensemble(
        base_request=req,
        request_id="test-3",
        strategy="longest",
        models=["model-fail", "model-slow"]
    )
    
    assert decision.resolved_model == "model-slow"


@pytest.mark.asyncio
async def test_ensembler_total_failure():
    router = DummyRoutingEngine()
    ensembler = ModelEnsembler(router)
    
    req = ChatRequest(
        model="default",
        messages=[Message(role="user", content="Hello")]
    )
    
    # If all fail, it should raise EnsemblerError
    with pytest.raises(EnsemblerError):
        await ensembler.execute_ensemble(
            base_request=req,
            request_id="test-4",
            strategy="fastest",
            models=["model-fail", "model-fail"]
        )
