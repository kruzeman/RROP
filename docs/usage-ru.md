# Сборка и запуск

[English](usage.md) · [Главная](../README.ru.md)

## ROM

Нужен исходный `Rings of Power (UE) [!].gen`, 1 048 576 байт, в формате raw
big-endian. Скрипт проверяет SHA-256:

```text
36303fc447c433ebc69c3d4df86c783c86b383e0acead1c19595f13269e248f5
```

Переименование другого дампа не поможет. ZIP/7z сначала нужно распаковать;
interleaved SMD напрямую не поддерживается. ROM предоставляет пользователь,
папка `roms/` исключена из Git.

## Linux

Требуются Python 3.10+, компиляторы C11/C++17, pkg-config, SDL2 и SDL2_ttf
с файлами разработки. Python использует стандартную библиотеку; установка
через pip для сборки из репозитория не нужна.

Ubuntu/Debian:

```sh
sudo apt update
sudo apt install git python3 build-essential pkg-config libsdl2-dev libsdl2-ttf-dev fonts-dejavu-core
```

Arch Linux:

```sh
sudo pacman -S --needed git python base-devel sdl2 sdl2_ttf ttf-dejavu
```

Fedora:

```sh
sudo dnf install git python3 gcc gcc-c++ make pkgconf-pkg-config SDL2-devel SDL2_ttf-devel dejavu-sans-fonts
```

Скачайте проект, положите свой ROM в `roms`, затем соберите:

```sh
git clone https://github.com/kruzeman/RROP.git
cd RROP
mkdir -p roms
# Перед следующей командой положите ROM в roms/.
python3 examples/build_rings_of_power.py 'roms/Rings of Power (UE) [!].gen' \
  --text-renderer rings-text
```

Сборка может занять несколько минут. Результат:
`build/rings-of-power/rings-of-power`. В обычную оконную сборку уже входят
вайдскрин, зум, плавная камера, мышь, сохранения и Settings. Звук ymfm включён
по умолчанию. Параметр `--text-renderer rings-text` добавляет внешний шрифт;
без него SDL2_ttf не требуется.

Запуск со всеми улучшениями:

```sh
./build/rings-of-power/rings-of-power --window --audio on \
  --widescreen --zoom --smooth-camera --mouse \
  --font /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf
```

Путь шрифта в примере — для Ubuntu/Debian. Укажите существующий TTF/OTF;
найти его можно через `fc-match -f '%{file}\n' 'DejaVu Sans'`.
Шрифты не включены в проект. Без `--font` отображается оригинальный текст.

Есть и короткий лаунчер:

```sh
./run-rings-of-power.sh --widescreen --zoom --smooth-camera --mouse
```

Классический режим выбирается в Settings. Сохранённые настройки имеют
приоритет над начальными флагами запуска.

## macOS (экспериментально)

Используется тот же скрипт сборки, что и в Linux. Нужны Python 3.10+,
Clang из Command Line Tools и SDL2 с pkg-config. Для внешних шрифтов
дополнительно нужен SDL2_ttf. Python-пакеты устанавливать не требуется.

Установите недостающие зависимости:

```sh
xcode-select --install
brew install python pkgconf sdl2-compat
# Необязательно, для внешнего текста:
brew install sdl2_ttf
```

[SDL2 compatibility layer](https://formulae.brew.sh/formula/sdl2-compat) и
[SDL2_ttf](https://formulae.brew.sh/formula/sdl2_ttf) доступны в Homebrew.
Уже установленная SDL2 также подходит.

Положите свой проверенный ROM в `roms/`, затем из папки проекта выполните:

```sh
python3 examples/build_rings_of_power.py 'roms/Rings of Power (UE) [!].gen'
./run-rings-of-power.command
```

Лаунчер можно открыть двойным щелчком в Finder. Сохранения и настройки
находятся в `saves/` внутри проекта. Для внешних шрифтов добавьте при сборке
`--text-renderer rings-text`, а при запуске — `--font /путь/к/шрифту.ttf`.

Для проверки инструмента без ROM игры: `make demo` и `make test`.
Проверки окна используют SDL dummy; видимое окно и звук проверяются
запуском игры из обычного Terminal/Finder. Сборка нативная для текущего Mac;
универсальный `.app` и переносимые библиотеки пока не упаковываются.

## Windows

### Кросс-сборка из Linux

Ubuntu/Debian:

```sh
sudo apt install python3 gcc-mingw-w64-x86-64 g++-mingw-w64-x86-64 \
  binutils-mingw-w64-x86-64 pkg-config ca-certificates
python3 examples/build_rings_windows.py 'roms/Rings of Power (UE) [!].gen'
```

Используются `x86_64-w64-mingw32-gcc`, соответствующий `g++` и `objdump`.
Если нужен явно выбранный POSIX-вариант:

```sh
python3 examples/build_rings_windows.py 'roms/Rings of Power (UE) [!].gen' \
  --cc x86_64-w64-mingw32-gcc-posix --cxx x86_64-w64-mingw32-g++-posix
```

Первая сборка загружает официальные MinGW SDK SDL2 2.32.10 и SDL2_ttf 2.24.0,
проверяет контрольные суммы и кеширует их в `build/windows-sdk`.
Linux-пакеты SDL для кросс-сборки не нужны.

### Сборка в Windows

Установите [MSYS2](https://www.msys2.org/), откройте **UCRT64**, выполните
`pacman -Syu`. Если потребуется, переоткройте терминал и повторите обновление.

```sh
pacman -S --needed git mingw-w64-ucrt-x86_64-python \
  mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-binutils \
  mingw-w64-ucrt-x86_64-pkgconf
git clone https://github.com/kruzeman/RROP.git
cd RROP
mkdir -p roms
# Положите свой ROM в roms/.
python examples/build_rings_windows.py 'roms/Rings of Power (UE) [!].gen' \
  --cc gcc --cxx g++ --objdump objdump
```

### Запуск

Результат: `build/rings-windows/RROP-Windows-x64.zip`. Распакуйте архив целиком
и запустите **Play.cmd**. DLL должны лежать рядом с `rings-of-power.exe`.
Для запуска не требуются Python, WSL или компилятор. Лаунчер использует
системный Arial; другой шрифт можно указать через `--font`.

PowerShell:

```powershell
.\rings-of-power.exe --window --audio on --widescreen --zoom --smooth-camera --mouse `
  --font "$env:WINDIR/Fonts/arial.ttf"
```

ZIP содержит встроенные в executable данные игры. Это локальный результат
сборки, в публичный исходный репозиторий он не включается.

## Управление

| Ввод | Действие |
| --- | --- |
| Стрелки | Направление на Genesis |
| Z / X / C | Кнопки A / B / C |
| Enter | Start; подтверждение в новых меню |
| F10 | Открыть/закрыть Settings |
| Esc | Открыть Settings; назад внутри новых меню |
| Settings → Exit | Выход |
| F5 / F9 | Выбор ручного сохранения / загрузки |
| Пробел | Пауза |
| Удерживать Tab | Ускорение |
| Колесо мыши | Зум 50–100%, если Zoom включён |
| Средняя кнопка / 0 | Вернуть 100% |
| Удерживать ЛКМ | Идти в направлении курсора на наружной карте |
| ПКМ | Один запуск штатного автохода A + направление |

Мышь задаёт направление, а не строит маршрут к произвольной точке.
Автоход останавливается на перекрёстках и интерактивных объектах.
В меню и фиксированных сценах команды наружной ходьбы не подаются.
Поддержка физических геймпадов и переназначение клавиш пока не реализованы;
Control settings — заглушка. **System → Help** переключает экранную подсказку
контроллера; изначально она выключена.

## Сохранения и настройки

Есть пять ручных слотов и пять вращающихся автосохранений. Интервал — пять
минут активного реального времени; пауза и новые меню в него не входят.
Штатные Save/Load/Continue открывают выбор слота. Стрелки вверх/вниз выбирают,
Enter, X или Z подтверждают, Esc возвращает назад.

Папки по умолчанию:

| ОС | Путь |
| --- | --- |
| Linux с абсолютным XDG_STATE_HOME | `$XDG_STATE_HOME/genesisrecomp/rings-of-power` |
| Остальные Linux | `~/.local/state/genesisrecomp/rings-of-power` |
| Windows | `%LOCALAPPDATA%/GenesisRecomp/rings-of-power` |

Старые пути сохранены для совместимости с предыдущими сборками.
Другую папку задаёт `--save-dir /путь/к/сейвам`.
Файлы: `manual-1.grs` … `manual-5.grs`, `auto-1.grs` … `auto-5.grs`
и `settings.cfg`. Перед обновлением делайте резервную копию папки.

Для загрузки нужен тот же ROM и режим звука: сейв из `--audio on`
загружайте с `--audio on`. Формат общий для Linux и Windows, но совместимость
с будущими версиями кода не гарантирована. Настройки отдельны от сейвов
и при загрузке не заменяются.

Это полные снимки машины: RAM, CPU, графика, звук. Они не повторяют очистку
временных таблиц оригинальным загрузчиком EEPROM. О проблеме долгой игры —
в [диагностике](diagnostics-ru.md).

## Headless и частые проблемы

Минимальная сборка без SDL и звукового backend:

```sh
python3 examples/build_rings_of_power.py 'roms/Rings of Power (UE) [!].gen' \
  --frontend headless --sound none
./build/rings-of-power/rings-of-power --headless --audio stub --limit 1000000
```

Она заменяет обычную оконную сборку по тому же пути. Чтобы сохранить обе,
укажите при сборке `--output build/rings-headless/rings-of-power`.

- `--sound ymfm` задаётся **при сборке**, `--audio on` — **при запуске**.
  Если звук не скомпилирован, пересоберите с backend по умолчанию.
  `--audio stub` выключает Z80 и не воспроизводит звук.
- `wrong ROM revision`: проверяйте checksum самого файла.
- Ошибка SDL/pkg-config: нужны пакеты разработки, а не только runtime.
- Не хватает Windows DLL: распакуйте весь ZIP, не один executable.
- Флаги не меняют отображение: `settings.cfg` имеет приоритет.
  Используйте Settings или после закрытия удалите только этот файл.
- `status=budget` в headless означает достижение указанного лимита инструкций.
  Для `status=fault` / `execution stopped` нужны адрес и commit сборки.
- Ошибка Void создаёт `diagnostics/void-error.txt` и, если возможно,
  `diagnostics/void-error.grs`. Причина ещё не исправлена.

После обновления исходников пересоберите executable: `git pull` сам бинарь
не обновляет.
