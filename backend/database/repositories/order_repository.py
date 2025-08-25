class OrderRepository:
    """Minimal shim for tests to patch methods on.

    Real implementations should provide async methods like:
    - get_order_by_id(order_id)
    - update_order_status(order_id, status)
    """

    async def get_order_by_id(self, order_id):  # pragma: no cover - shim
        return None

    async def update_order_status(self, order_id, status):  # pragma: no cover - shim
        return {"id": order_id, "status": status}
