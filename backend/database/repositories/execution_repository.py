class ExecutionRepository:
    """Minimal shim for tests to patch methods on.

    Real implementations should provide async methods like:
    - get_executions_for_order(order_id)
    - create_execution(execution_data)
    """

    async def get_executions_for_order(self, order_id):  # pragma: no cover - shim
        return []

    async def create_execution(self, execution_data):  # pragma: no cover - shim
        return {"id": "exec_mock", **execution_data}
