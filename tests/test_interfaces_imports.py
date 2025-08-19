def test_can_import_all_protocols():
    # Import must succeed and expose the expected names
    import ghconcat.core.interfaces as I

    assert hasattr(I, "AIProcessorProtocol")
    assert hasattr(I, "ExecutionEngineProtocol")
    assert hasattr(I, "FileDiscoveryProtocol")
    assert hasattr(I, "PathResolverProtocol")
    assert hasattr(I, "HTTPTransportProtocol")
    assert hasattr(I, "UrlFetcherProtocol")
    assert hasattr(I, "ReaderProtocol")
    assert hasattr(I, "ReaderRegistryProtocol")
    assert hasattr(I, "RendererProtocol")
    assert hasattr(I, "TemplateEngineProtocol")
    assert hasattr(I, "TextTransformerProtocol")
    assert hasattr(I, "ReplaceSpec")