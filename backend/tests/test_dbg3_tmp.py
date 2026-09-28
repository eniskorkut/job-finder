import logging

def test_dbg3(pytestconfig):
    logger = logging.getLogger("httpx")
    original = logging.Logger.__setattr__
    def traced(self, name, value):
        if name == "disabled" and value and self.name == "httpx":
            import traceback
            print("TRACE disable httpx:")
            traceback.print_stack()
        original(self, name, value)
    logging.Logger.__setattr__ = traced
    try:
        logging.getLogger("httpx").disabled = False
        # simulate pytest's per-test setup hook ordering by re-importing
        import app.main  # noqa
    finally:
        logging.Logger.__setattr__ = original
    print("after:", logger.disabled)
