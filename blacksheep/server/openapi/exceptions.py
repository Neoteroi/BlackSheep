class DocumentationException(Exception):
    pass


class DuplicatedContentTypeDocsException(DocumentationException):
    def __init__(self, content_type: str) -> None:
        super().__init__(
            f"A documentation element for content type {content_type} "
            "has already been specified. Ensure that response content items "
            "have unique type."
        )
        self.content_type = content_type
