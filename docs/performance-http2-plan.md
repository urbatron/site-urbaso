# План включения HTTP/2 на общих HTTPS-слушателях

**Статус: требуется согласие на изменение протокола всех перечисленных сайтов.**
Это предложение для проверки. Сервер не изменён, установщик не подготовлен.
HTTP/2 сам по себе не гарантирует PageSpeed выше 90.

Диагностика VPS: Nginx 1.24.0 (Ubuntu), OpenSSL 3.0.13, модуль HTTP/2 имеется.
Активны общие сокеты `0.0.0.0:443` и `[::]:443`. Проверка сертификатов и ALPN
для urbaso.ru, site.urbaso.ru и www.urbaso.ru на обеих loopback-версиях IP
подтвердила HTTP/1.1. Остальные сайты ещё требуют исходных проверок.

В этой версии `listen ... http2` включает протокол для общего адреса и порта.
Добавления параметра только в urbaso достаточно для общего эффекта, но оно
не ограничивает эффект этим сайтом. Отдельный `http2 on` в `server` появился
в 1.25.1. В рамках этого плана пакеты, адреса и схема TLS не меняются.

## Точная область

Пути ниже относительно `/etc/nginx/sites-enabled/`. Всего **21 файл, 31 имя
HTTPS-сайта, 22 TLS-блока server, 39 директив listen: 22 IPv4 и 17 IPv6**.
Числа в двух последних столбцах обозначают директивы, а не имена сайтов.

| Файл | Имена HTTPS-сайтов | IPv4 | IPv6 |
|---|---|---:|---:|
| `adminer.urbaso.ru.conf` | `adminer.urbaso.ru` | 1 | 0 |
| `direct.semora.ru` | `direct.semora.ru` | 1 | 1 |
| `disiner.ru.conf` | `disiner.ru`, `www.disiner.ru` | 1 | 1 |
| `diski-rts.ru.conf` | `diski-rts.ru`, `www.diski-rts.ru` | 1 | 0 |
| `doc.pansionat-dobry.ru.conf` | `doc.pansionat-dobry.ru` | 1 | 1 |
| `intersurgical.urbaso.ru.conf` | `intersurgical.urbaso.ru` | 1 | 1 |
| `panel.sitetops.ru` | `panel.sitetops.ru`, `www.panel.sitetops.ru` | 1 | 1 |
| `powercube.urbaso.ru.conf` | `powercube.urbaso.ru` | 1 | 1 |
| `prodvizheniyesaytov.ru.conf` | `prodvizheniyesaytov.ru`, `www.prodvizheniyesaytov.ru` | 1 | 1 |
| `review.semora.ru` | `review.semora.ru` | 1 | 1 |
| `rts-servis.com.conf` | `rts-servis.com` | 1 | 1 |
| `semora.ru` | `semora.ru`, `www.semora.ru` | 1 | 1 |
| `site.urbaso.ru.conf` | `site.urbaso.ru` | 1 | 1 |
| `sitetops.ru.conf` | `sitetops.ru`, `www.sitetops.ru` | 1 | 1 |
| `skgoldstroy.urbaso.ru.conf` | `skgoldstroy.urbaso.ru` | 1 | 1 |
| `staltet.ru` | `staltet.ru`, `www.staltet.ru` | 1 | 1 |
| `support-test.urbaso.ru.conf` | `support-test.urbaso.ru` | 1 | 0 |
| `tnvd-rts.ru.conf` | `tnvd-rts.ru`, `www.tnvd-rts.ru` | 1 | 0 |
| `trade.semora.ru` | `trade.semora.ru` | 1 | 1 |
| `urbaso.ru.conf` | `urbaso.ru`, `www.urbaso.ru` | 2 | 2 |
| `urbatravel.ru.conf` | `urbatravel.ru`, `www.urbatravel.ru` | 1 | 0 |

`new.cucina-msk.ru` слушает только HTTP и в область изменения не входит.
Новые IPv6-слушатели не добавляются: проверяются 31 имя через IPv4 и только
23 имени с имеющимся IPv6-listen через IPv6, всего 54 пары имя/семейство IP.

## Минимальная правка после согласования

Во всех 39 существующих SSL-listen добавить только токен `http2` после `ssl`.
Например, `listen [::]:443 ssl ipv6only=on;` станет
`listen [::]:443 ssl http2 ipv6only=on;`. Остальные токены, комментарии, порты,
сертификаты, TLS-параметры, маршруты, upstream, gzip и кеширование сохраняются.
Единообразная запись делает общую настройку явной и исключает смешение
протокольных параметров одного слушателя. `http2 on;` на 1.24 не используется.

## Проверки и откат

1. Сверить версию, модуль, оба сокета и точный inventory выше; выполнить
   `nginx -t`. Сохранить SHA256 всех активных nginx-файлов, реальные пути,
   цели symlink, владельцев и права. Подтвердить наличие клиента с HTTP/2
   для проверки реальных запросов, например соответствующую сборку curl.
2. До изменения проверить все 54 пары через loopback с правильным SNI,
   проверкой CA и имени сертификата: ALPN, HTTP/1.1 GET `/`, статус и Location.
   TLS/сетевые ошибки, неожиданные 4xx и любые 5xx останавливают работу.
   Ожидаемые 401/403 закрытых страниц предварительно сверяются с правилами
   доступа; проверка сертификатов нигде не отключается.
3. Создать резервные копии, metadata с исходными/планируемыми SHA256 и отдельную
   команду отката вне webroot, в `/root/backups/nginx-http2-*`. Показать diff:
   ровно 39 добавлений токена в согласованных файлах. Перед каждой записью
   повторно проверить хеши и symlink; при внешних изменениях остановиться.
4. Атомарно записать реальные файлы, сохранив ссылки, владельцев и права.
   Повторить `nginx -t`, проверить отсутствие новых предупреждений и изменений
   остальных конфигов. Выполнить graceful reload, без restart.
5. Для всех 54 пар проверить ALPN `h2`, реальный HTTP/2 GET и отдельный
   HTTP/1.1 GET с проверкой TLS. HTTP/2-клиент обязан подтвердить именно версию 2,
   а не скрытый fallback. Статусы и Location должны совпасть с baseline;
   динамические HTML не сравниваются побайтно. Для urbaso дополнительно
   проверить байты HTML/CSS, gzip, Cache-Control, редиректы и закрытые пути.
6. При ошибке вернуть собственные изменённые файлы из backup, выполнить
   `nginx -t` и reload прежней конфигурации. Ничего не удалять. Перед откатом
   текущие хеши должны соответствовать исходной или применённой версии;
   неизвестные последующие правки не перезаписывать. После отката проверить
   исходные ALPN, статусы и редиректы. Копии и журнал сохранить.

После серверных проверок повторить публичный PageSpeed для обоих устройств.
Разрешение на этот общий эффект требуется отдельно от оптимизации urbaso.ru.

Основание: [документация HTTP/2](https://nginx.org/en/docs/http/ngx_http_v2_module.html),
[официальное изменение выбора протокола по SNI](https://mailman.nginx.org/pipermail/nginx-devel/2023-June/4AQ7ABVFMO4EV5IR6LHENRUNGZQPYMOI.html),
[исходный код Nginx 1.24.0](https://github.com/nginx/nginx/blob/release-1.24.0/src/http/ngx_http.c).
