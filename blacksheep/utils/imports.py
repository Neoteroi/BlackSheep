

class OptionalModuleNotFoundError(RuntimeError):
    """Exception risen when an optional module is not installed, and is required in a given context."""

    def __init__(self, optional_module_name: str):
        super().__init__(f'The module "{optional_module_name}" is required in this context. '
                         f'To resolve this error, install the extra with: '
                         f'`pip install {optional_module_name}`')
        self.optional_module_name = optional_module_name

    @classmethod
    def replace_function(cls, asynchronous: bool = False, *args):
        if asynchronous:
            async def raising_function(*args, **kwargs):
                raise cls()
        else:
            def raising_function(*args, **kwargs):
                raise cls()
        return raising_function
