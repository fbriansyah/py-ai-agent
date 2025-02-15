import pika
import logfire
from pika import BlockingConnection
from pika.exchange_type import ExchangeType

class QueueConfig:
    exchange: str
    queue: str
    routing_key: str
    def __init__(self, exchange: str, queue: str, routing_key: str):
        self.exchange = exchange
        self.queue = queue
        self.routing_key = routing_key
        
queue_configs = {
    "ai.upload": QueueConfig("py-agent.upload", "file-proccess.ai", "q.file-proccess.ai")
}

class RabbitClient:
    conn: BlockingConnection
    def __init__(self, host: str, port: str, username: str, password: str):
        logfire.info(f"Connect Rabbit {host}:{port}")
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        credentials = pika.PlainCredentials(username, password)
        conn = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=host, 
                port=port, 
                credentials=credentials
            )
        )
        self.conn = conn
        self.channel = conn.channel()
        
    def setup(self):
        with logfire.span("rabbitmq.setup"):
            for key in queue_configs:
                logfire.info(f"Setting up queue for {key}")
                config = queue_configs[key]
                self.channel.exchange_declare(
                    config.exchange, 
                    exchange_type=ExchangeType.topic
                )
                self.channel.queue_declare(config.queue)
                self.channel.queue_bind(
                    exchange=config.exchange, 
                    queue=config.queue, 
                    routing_key=config.routing_key
                )
                
    def publish(self, key: str, message: str):
        with logfire.span("rabbitmq.publish"):
            # check key exists
            if key not in queue_configs:
                raise Exception(f"Queue config not found for {key}")
            
            config = queue_configs[key]
            self.channel.basic_publish(
                exchange=config.exchange, 
                routing_key=config.routing_key, 
                body=message
            )
    
    def get_channel(self):
        return self.channel