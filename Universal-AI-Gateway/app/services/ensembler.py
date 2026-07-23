"""
Model Ensembling Service.
Executes concurrent requests against multiple frontier LLM models and uses
a voting or heuristic selection strategy to return the optimal response.
"""

import asyncio
from typing import List, Tuple
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.router import RoutingEngine, RoutingDecision
from app.core.logging import get_logger

logger = get_logger(__name__)

class EnsemblerError(Exception):
    """Raised when all ensemble executions fail."""
    pass

class ModelEnsembler:
    """Executes multiple LLM inferences concurrently and returns the best hit."""
    
    def __init__(self, routing_engine: RoutingEngine):
        self._router = routing_engine
        
    async def execute_ensemble(
        self, 
        base_request: ChatRequest, 
        request_id: str,
        strategy: str,
        models: List[str]
    ) -> Tuple[ChatResponse, RoutingDecision]:
        """
        Takes a base ChatRequest and a list of models, duplicates the request
        for each model, executes them concurrently in the routing engine,
        and selects the winner.
        """
        if not models:
            raise ValueError("Ensemble models list cannot be empty")
            
        logger.info(f"Starting model ensemble using strategy '{strategy}' across models: {models}")
            
        tasks = []
        for model in models:
            # Create a cloned request isolating the assigned model
            cloned_req = base_request.model_copy(deep=True)
            cloned_req.model = model
            tasks.append(self._router.route_request(cloned_req, request_id=request_id))
            
        if strategy == "fastest" or strategy == "first":
            # True short-circuiting: return whichever resolves first
            done, pending = await asyncio.wait(
                [asyncio.create_task(t) for t in tasks], 
                return_when=asyncio.FIRST_COMPLETED
            )
            # Cancel remaining tasks to save tokens/connections
            for p in pending:
                p.cancel()
                
            first_finished = list(done)[0]
            try:
                winner = first_finished.result()
            except Exception as e:
                raise EnsemblerError(f"Fastest execution failed: {str(e)}")
        else:
            # Gather all for length-based or consensus vote
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            valid_responses: List[Tuple[ChatResponse, RoutingDecision]] = []
            for res in results:
                if isinstance(res, Exception):
                    logger.warning(f"Ensemble execution slice failed: {str(res)}")
                else:
                    valid_responses.append(res)
                    
            if not valid_responses:
                raise EnsemblerError("All ensembled model requests failed.")
                
            if strategy == "longest":
                # Return the response with the most completion tokens
                winner = max(
                    valid_responses, 
                    key=lambda x: x[0].usage.completion_tokens if x[0].usage else 0
                )
            else:
                winner = valid_responses[0]
            
        logger.info(f"Ensemble winner selected: {winner[1].resolved_model} via {winner[1].provider}")
        return winner
