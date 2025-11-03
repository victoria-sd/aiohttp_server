import os
import asyncio
import logging
from aiohttp import web
import json

WS_FILE = os.path.join(os.path.dirname(__file__), "websocket.html")
SERVER_HOST = 'localhost'
SERVER_PORT = 8080
PING_INTERVAL_MS = 10000  # Интервал для отправки PING клиентам (для проверки соединения)

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

connected_clients = set()


async def send_to_all_clients(message: str):
    """
    Асинхронно рассылает сообщение всем подключенным веб-сокет клиентам,
    с обработкой ошибок и удалением неактивных соединений.
    """
    to_remove = []
    for client in list(connected_clients):
        try:
            # Проверка, что соединение не закрыто
            if client.closed:
                logger.warning(f"Client {id(client)} is already closed, marking for removal.")
                to_remove.append(client)
                continue

            # Попытка отправить сообщение
            await client.send_str(message)

        except ConnectionResetError:
            # Клиент резко оборвал соединение
            logger.warning(f"Client {id(client)} ConnectionResetError, marking for removal.")
            to_remove.append(client)
        except Exception as e:
            # Ловим любые другие ошибки, связанные с отправкой (например, сокет уже закрыт)
            logger.error(f"Error sending message to client {id(client)}: {type(e).__name__}. Marking for removal.")
            to_remove.append(client)

    # Удаляем неактивные соединения из списка
    for client in to_remove:
        if client in connected_clients:
            connected_clients.remove(client)
            logger.info(f"Removed disconnected client {id(client)} from active list.")


async def wshandler(request: web.Request):
    """
    Обработчик для подключения веб-сокетов.
    """
    resp = web.WebSocketResponse()
    available = resp.can_prepare(request)

    if not available:
        with open(WS_FILE, "rb") as fp:
            return web.Response(body=fp.read(), content_type="text/html")

    await resp.prepare(request)
    client_id = str(id(resp))  # Уникальный идентификатор для клиента (по объекту)
    logger.info(f"Client connected via WebSocket: {client_id}")

    await resp.send_str("Welcome!!!")
    await send_to_all_clients("Someone joined.")
    connected_clients.add(resp)

    try:
        async for msg in resp:
            # Обработка входящих сообщений от клиента
            if msg.type == web.WSMsgType.TEXT:
                logger.info(f"Received from {client_id}: {msg.data}")
                if msg.data == 'ping':
                    # Отвечаем на ping от клиента, чтобы он знал, что сервер жив
                    await resp.send_str('pong')
                    logger.debug(f"Sent pong to client {client_id}")
                else:
                    # Если это не ping, рассылаем как новость остальным
                    await send_to_all_clients(f"Client {client_id}: {msg.data}")
            elif msg.type == web.WSMsgType.PING:
                # aiohttp сам обрабатывает PING, но мы можем ответить PONG явно
                await resp.pong()
                logger.debug(f"Received PING from client {client_id}, sent PONG.")
            elif msg.type == web.WSMsgType.CLOSE:
                logger.info(f"Client {client_id} sent close frame.")
                break  # Выход из цикла при закрытии соединения
            else:
                logger.warning(f"Received unexpected message type from {client_id}: {msg.type}")
        return resp  # Возвращаем response после выхода из цикла (для корректного завершения)

    except Exception as e:
        logger.error(f"Error in websocket handler for client {client_id}: {e}")

    finally:
        # Очистка при отключении клиента
        if resp in connected_clients:
            connected_clients.remove(resp)
            logger.info(f"Client disconnected: {client_id}")
            await send_to_all_clients("Someone disconnected.")

            if not resp.closed:  # Проверяем, что соединение еще не закрыто
                await resp.close()

        elif not resp.closed:
            await resp.close()

    return resp


async def post_news(request):
    """
    Обработчик для приема новых новостей методом POST /news.
    Рассылает полученную новость всем подключившимся веб-сокет клиентам.
    """
    try:
        data = await request.json()
        news_item = data.get('news')

        if not news_item:
            return web.Response(status=400, text="Bad Request: 'news' field is missing in JSON payload.")

        logger.info(f"Received news via POST /news: {news_item}")
        await send_to_all_clients(f"NEWS: {news_item}")  # Добавляем префикс "NEWS:" для ясности

        return web.Response(status=200, text="News sent successfully.")

    except asyncio.TimeoutError:
        logger.error("Timeout receiving JSON payload for POST /news.")
        return web.Response(status=408, text="Request Timeout.")
    except json.JSONDecodeError:
        logger.error("Invalid JSON format for POST /news.")
        return web.Response(status=400, text="Bad Request: Invalid JSON format.")
    except Exception as e:
        logger.error(f"Error processing POST /news: {e}")
        return web.Response(status=500, text="Internal Server Error.")


async def on_shutdown(app: web.Application):
    """
    Обработчик для корректного завершения работы сервера.
    Закрывает все активные веб-сокет соединения.
    """
    logger.info("Shutting down server. Closing all WebSocket connections...")
    # Создаем список задач для закрытия сокетов, чтобы выполнялось параллельно
    shutdown_tasks = [client.close() for client in connected_clients]
    await asyncio.gather(*shutdown_tasks)
    connected_clients.clear()
    logger.info("All WebSocket connections closed.")


def init():
    app = web.Application()
    app.router.add_static('/static/', path=os.path.join(os.path.dirname(__file__), 'static'))
    app.router.add_get("/", wshandler)

    # Добавляем обработчик для POST /news
    app.router.add_post("/news", post_news)

    # Добавляем обработчик для закрытия веб-сокетов при выключении сервера
    app.on_shutdown.append(on_shutdown)

    logger.info(f"WebSocket file configured as: {WS_FILE}")
    return app


async def run_server():
    """
    Основная асинхронная функция для запуска сервера.
    """
    app = init()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, SERVER_HOST, SERVER_PORT)
    await site.start()
    logger.info(f"Server started on http://{SERVER_HOST}:{SERVER_PORT}")

    # Держим сервер запущенным (бесконечно, пока не прервем)
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        logger.info("Server is shutting down.")
    finally:
        await runner.cleanup()
        logger.info("Server stopped.")


if __name__ == '__main__':
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        logger.info("Server stopped by user (Ctrl+C).")