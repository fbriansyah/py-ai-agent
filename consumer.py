import pika, sys, os
import logfire

from dotenv import load_dotenv, get_key
from databases.rabbitmq import RabbitClient, queue_configs
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic, BasicProperties

from services.file_processor import FileProcessor

# load the config from dot env file
load_dotenv()

logfire.configure(send_to_logfire='if-token-present', token=get_key(".env", "LOGFIRE_KEY"))

def ai_upload_callback(ch: BlockingChannel, method: Basic.Deliver, properties: BasicProperties, body: bytes):
    file_name: str = body.decode()
    with logfire.span('ai_upload_callback'):
        logfire.info(f'Processing {file_name}')
        file_processor = FileProcessor(file_name)
        
        file_processor.process_file()
        ch.basic_ack(delivery_tag = method.delivery_tag)

def main():
    # listen rabbitmq
    rabbit_client = RabbitClient(
        host=get_key(".env", "RABBIT_HOST"),
        port=get_key(".env", "RABBIT_PORT"),
        username=get_key(".env", "RABBIT_USER"),
        password=get_key(".env", "RABBIT_PASS")
    )
    rabbit_client.setup()
    channel = rabbit_client.get_channel()

    channel.basic_consume(queue=queue_configs["ai.upload"].queue, on_message_callback=ai_upload_callback)

    print(' [*] Waiting for messages. To exit press CTRL+C')
    channel.start_consuming()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print('Interrupted')
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)