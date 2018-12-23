

cdef class ServerLimits:

    def __init__(self, 
                 int keep_alive_timeout = 300,
                 int max_body_size = 1024 * 1024 * 24):
        self.max_body_size = max_body_size
        self.keep_alive_timeout = keep_alive_timeout


cdef class ServerOptions:

    def __init__(self,
                 str host,
                 int port,
                 bint no_delay = 1,
                 int processes_count = 1,
                 int backlog = 1000,
                 bint show_error_details = False,
                 ServerLimits limits = None,
                 object ssl_context = None):
        if limits is None:
            limits = ServerLimits()

        self.show_error_details = show_error_details
        self.no_delay = no_delay
        self.host = host
        self.port = port
        self.processes_count = processes_count
        self.backlog = backlog
        self.limits = limits
        self.ssl_context = ssl_context

    def set_ssl(self, ssl_context):
        self.ssl_context = ssl_context
