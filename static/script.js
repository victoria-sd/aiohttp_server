    $(function() {
      var conn = null;
      var pingInterval = null;
      var PING_INTERVAL_MS = 60000;
      var PONG_TIMEOUT_MS = 5000;
      var pongReceived = true;
      var pongTimeoutId = null;

      function log(msg) {
        var control = $('#log');
        // Создаем новый div для каждой записи лога
        var msgDiv = $('<div>').html(msg);
        control.prepend(msgDiv); // Добавляем новую запись в начало
        // Ограничиваем количество записей, чтобы не переполнять DOM
        if (control.children().length > 100) {
            control.children().last().remove();
        }
      }
      function connect() {
        disconnect();
        var wsScheme = (window.location.protocol == 'https:' ? 'wss://' : 'ws://');
        var wsUri = wsScheme + window.location.host;
        conn = new WebSocket(wsUri);
        log('Connecting...');
        conn.onopen = function() {
          log('Connected.');
          pongReceived = true;
          startPingPong();
          update_ui();
        };
        conn.onmessage = function(e) {
          log('Received: ' + e.data);
          if (e.data === 'pong') {
              clearTimeout(pongTimeoutId);
              pongReceived = true;
          }
        };
        conn.onclose = function(e) {
          log('Disconnected. Code: ' + e.code);
          conn = null;
          stopPingPong();
          update_ui();
          setTimeout(connect, 5000);
        };
        conn.onerror = function(error) {
            log('WebSocket Error occurred.');
            stopPingPong();
        }
      }
      function disconnect() {
        if (conn != null) {
          log('Disconnecting...');
          conn.close();
          conn = null;
          stopPingPong();
          update_ui();
        }
      }
      function update_ui() {
        if (conn == null) {
          $('#status').text('disconnected');
          $('#connect').html('Connect');
        } else {
          $('#status').text('connected');
          $('#connect').html('Disconnect');
        }
      }

      function sendPing() {
        if (conn && conn.readyState === WebSocket.OPEN) {
            conn.send('ping');
            pongReceived = false;

            pongTimeoutId = setTimeout(() => {
                if (!pongReceived) {
                    log('Pong timeout! Disconnecting...');
                    conn.close(1008, "Pong timeout");
                }
            }, PONG_TIMEOUT_MS);
        }
      }

      function startPingPong() {
        stopPingPong();
        pingInterval = setInterval(sendPing, PING_INTERVAL_MS);
      }

      function stopPingPong() {
        if (pingInterval) {
            clearInterval(pingInterval);
            pingInterval = null;
        }
        if (pongTimeoutId) {
            clearTimeout(pongTimeoutId);
            pongTimeoutId = null;
        }
      }

      $('#connect').click(function() {
        if (conn == null) {
          connect();
        } else {
          disconnect();
        }
        update_ui();
        return false;
      });
      $('#send').click(function() {
        var text = $('#text').val();
        if (text.trim() === '') return false; // Не отправлять пустые сообщения
        log('Sending: ' + text);
        conn.send(text);
        $('#text').val('').focus();
        return false;
      });
      $('#text').keyup(function(e) {
        if (e.keyCode === 13) {
          $('#send').click();
          return false;
        }
      });

      update_ui();
    });