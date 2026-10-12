# phar: история и классы уязвимостей (php-src, 2021-09 → 2026-08)

_Исследование 2026-09-09. 200+ коммитов в ext/phar за 5 лет. Категоризация по ценности._


## Масштаб и характер
Не столько новые функции, сколько **циклы рефакторинга + накопившиеся security-фиксы**.
Два плотных всплеска: гига-`zend_string*` рефакторинг (апрель-май 2026) и цепочка
symlink/UAF/leak фиксов (май-август 2026). Число коммитов завышено merge-каскадами
PHP-8.2/8.3/8.4/8.5 (одни правки применяются 5×).


## 1. Security-класс (главное для мейнтейнера)
| Дата | Проблема |
|---|---|
| 2026-08 | UAF mounted phar subdir (GH-23418, #23442) |
| 2026-08 | memleak duplicate native manifest entries (GH-23477) |
| 2026-07 | GHSA-vc5h-9ppw-p5f3: circular symlink crash |
| 2026-05 | harden OpenSSL signature handling (#22174) |
| 2026-05 | PharData::getContent() crash on infinite recursion + symlink (GH-21986) |
| 2025-10 | fd-leak phar_zip_flush(); memleak gzip/openssl-polyfill; double-free Windows |
| 2025-11 | assertion-failure crashes (fseek OOB, stream-filter params); fflush() return fix |

Паттерн: **phar-обработка путей/симлинков не рассчитана на враждебные архивы**.
tar с произвольными symlink-entry, циклами, `..`/mount — атакующая поверхность.


## 2. Корневые механизмы (разбор трёх 2026-уязвимостей)

### 2.1 GHSA-vc5h + GH-21986 — ОДНА функция `phar_get_link_source()`, два поколения патчей
Наивная рекурсия `return phar_get_link_source(link_entry);`. tar позволяет
`a->b`, `b->a` → рекурсия никогда не завершается → stack overflow → SIGSEGV.

| Патч | Механизм | Замечание |
|---|---|---|
| GH-21986 (May, b2de3cf1) | depth-limit (`depth > max_depth = nEntries`) | требует hash-count на вызов |
| GHSA-vc5h (Jul, 2e0fa0a4) | **Floyd cycle detection** (slow/fast) | const-mem, точное обнаружение цикла |

July-патч надёжнее (точный detect, нет hash-count); фактически перезаписал May-патч.
Classic: сначала quick-fix recursion, потом более идиоматичный алгоритм поверх.

### 2.2 GH-23418 — UAF на `path`
`phar_get_entry_info_dir()`: нашёл `test` (путь из ключа манифеста), зовёт
`phar_mount_entry(phar, test, test_len, path, path_len)` — монтирует файл-как-директорию
на лету. Затем использует `path` для `zend_hash_str_find_ptr(&phar->manifest, path, path_len)`.
**`path` могла быть освобождена внутри `phar_mount_entry()`** (та переписывает/укорачивает
путь) → UAF.

Фикс: `mount_path = estrndup(path, path_len)` до вызова (null-terminated, переживает
`phar_mount_entry`); `test` держится до конца error-format/manifest-lookup.

**Класс:** временный буфер-параметр, переданный в функцию, которая (неизвестно
вызывающему) может его освободить. `char*` без явного len/иматируемости.


## 3. Связь с `zend_string*`-рефакторингом (апрель-май 2026)
Гига-миграция internals phar с raw `char*` на `zend_string*` (#217xx-#219xx). Это НЕ
косметика, а **систематическое устранение класса**: `zend_string` несёт len и живёт
по refcount (не `efree`-по-указателю). Поэтому:
- UAF-класс (2.2) рефакторинг **снимает системно** (refcount, нет незаметного free)
- symlink-цикл НЕ решается zend_string (нужен именно Floyd) — обезболивающие остаются
- `zend_string` делает сбои детектируемыми, а не segfault-тихими

**Вывод:** рефакторинг — правильный курс; symlink-патчи — постоянный остаток;
UAF-класс уйдёт с `zend_string*`. Пример регрессии от рефакторинга:
`#21943 "Fix path overread from recent refactoring"` — та же функция.

## 4. Behavioral-изменения (ломающие совместимость)
- 2026-08: **только `.phar` расширение триггерит авто-детект архива** (#23260) — сужение
- 2026-06: `.phar`-префикс non-magic dir handling (#22372)
- 2026-06: ZIP extra field length underflow (#22330)
- 2025-11: case-insens `__halt_compiler()` при чтении stub (GH-20442)
- 2025-10: freeing phar alias может инвалидировать PharFileInfo (GH-20302)
- 2025-05: `.phar` magic-directory preservation в `addEmptyDir()`

## 5. Рекомендация (если задача — аудит phar при портировании)
Актуальный риск потребления phar-файлов: **2025-11 assertion-crashes, 2026-05/07/08
UAF + symlink-recurка**. Для FreeUnit-порта: трактовать phar как враждебный ввод,
ограничить глубину цепочки ссылок, и — если идёт портирование на Rust/иное →
`zend_string`-эквивалент (len + refcount) снимает класс UAF.
