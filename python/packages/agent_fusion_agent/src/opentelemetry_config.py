"""OpenTelemetry配置模块

提供OpenTelemetry的基础配置和设置。
"""

import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.sqlite3 import SQLite3Instrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.asyncio import AsyncIOInstrumentor


def setup_opentelemetry(
    service_name: str = "agent-fusion",
    service_version: str = "1.0.0",
    jaeger_endpoint: str = "http://localhost:14268/api/traces",
    console_export: bool = True
):
    """设置OpenTelemetry追踪
    
    Args:
        service_name: 服务名称
        service_version: 服务版本
        jaeger_endpoint: Jaeger导出端点
        console_export: 是否输出到控制台
    """
    
    # 创建资源
    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: service_version,
        "environment": os.getenv("ENVIRONMENT", "development"),
        "host.name": os.getenv("HOSTNAME", "localhost")
    })
    
    # 设置追踪器提供者
    trace.set_tracer_provider(TracerProvider(resource=resource))
    tracer_provider = trace.get_tracer_provider()
    
    # 添加导出器
    exporters = []
    
    # 控制台导出器（开发环境）
    if console_export:
        console_exporter = ConsoleSpanExporter()
        console_processor = BatchSpanProcessor(console_exporter)
        tracer_provider.add_span_processor(console_processor)
    
    # Jaeger导出器（生产环境）
    try:
        jaeger_exporter = JaegerExporter(
            endpoint=jaeger_endpoint,
        )
        jaeger_processor = BatchSpanProcessor(jaeger_exporter)
        tracer_provider.add_span_processor(jaeger_processor)
        print(f"✓ Jaeger exporter configured: {jaeger_endpoint}")
    except Exception as e:
        print(f"⚠ Jaeger exporter failed: {e}")
    
    # 自动仪表化
    setup_auto_instrumentation()
    
    print(f"✓ OpenTelemetry configured for service: {service_name}")


def setup_auto_instrumentation():
    """设置自动仪表化"""
    try:
        # HTTP请求自动追踪
        RequestsInstrumentor().instrument()
        print("✓ Requests instrumentation enabled")
        
        # SQLite数据库自动追踪
        SQLite3Instrumentor().instrument()
        print("✓ SQLite3 instrumentation enabled")
        
        # 日志自动追踪
        LoggingInstrumentor().instrument()
        print("✓ Logging instrumentation enabled")
        
        # 异步操作自动追踪
        AsyncIOInstrumentor().instrument()
        print("✓ AsyncIO instrumentation enabled")
        
    except Exception as e:
        print(f"⚠ Auto instrumentation setup failed: {e}")


def get_tracer(name: str = __name__):
    """获取追踪器实例
    
    Args:
        name: 追踪器名称
        
    Returns:
        追踪器实例
    """
    return trace.get_tracer(name)


def cleanup_opentelemetry():
    """清理OpenTelemetry资源"""
    try:
        tracer_provider = trace.get_tracer_provider()
        if hasattr(tracer_provider, 'shutdown'):
            tracer_provider.shutdown()
        print("✓ OpenTelemetry resources cleaned up")
    except Exception as e:
        print(f"⚠ OpenTelemetry cleanup failed: {e}")


# 默认配置
if __name__ == "__main__":
    setup_opentelemetry() 