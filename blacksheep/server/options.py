

class ServerLimits:

    __slots__ = ('keep_alive_timeout', 
                 'max_body_size')

    def __init__(self,
                 keep_alive_timeout=300,
                 max_body_size=1024 * 1024 * 24):
        self.keep_alive_timeout = keep_alive_timeout
        self.max_body_size = max_body_size


class ServerOptions:

    __slots__ = ('host',
                 'port',
                 'no_delay',
                 'processes_count',
                 'limits',
                 'show_error_details',
                 'backlog')

    def __init__(self,
                 host,
                 port,
                 no_delay=1,
                 processes_count=1,
                 backlog=1000,
                 show_error_details=False,
                 limits=None):
        if limits is None:
            limits = ServerLimits()

        self.show_error_details = show_error_details
        self.no_delay = no_delay
        self.host = host
        self.port = port
        self.processes_count = processes_count
        self.backlog = backlog
        self.limits = limits
