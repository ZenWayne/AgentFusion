from opentelemetry import trace, baggage
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter as OTLPSpanGrpcExporter
from opentelemetry.sdk.resources import DEPLOYMENT_ENVIRONMENT, HOST_NAME, Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

def configure_oltp_tracing(endpoint: str = None) -> trace.TracerProvider:
    # 设置服务名、主机名
    resource = Resource(attributes={
        SERVICE_NAME: "autogen_demo",
        SERVICE_VERSION: "1.0",
        DEPLOYMENT_ENVIRONMENT: "windows",
        HOST_NAME: "localhost" # 请将 ${hostName} 替换为主机名
    })
    
    # 使用GRPC协议上报
    span_processor = BatchSpanProcessor(OTLPSpanGrpcExporter(
        endpoint="http://tracing-analysis-dc-sz.aliyuncs.com:8090",
        headers=("Authentication=fgo4jmqn0y@503dd021c8af556_fgo4jmqn0y@53df7ad2afe8301")
    ))
    
    trace_provider = TracerProvider(resource=resource, active_span_processor=span_processor)
    trace.set_tracer_provider(trace_provider)

    return trace_provider