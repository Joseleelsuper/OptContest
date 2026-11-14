#include "../solvers/cpp/ig.hpp"
#include <commctrl.h>
#include <commdlg.h>
#include <array>
#include <chrono>
#include <filesystem>
#include <mutex>
#include <thread>

namespace {
using Clock = std::chrono::steady_clock;
constexpr double cpu_budget = 57;
constexpr int open_id = 100, optimize_id = 101, ordered_id = 102, chart_id = 103;
constexpr COLORREF background = RGB(245, 247, 250);
constexpr COLORREF ink = RGB(21, 37, 55);
constexpr COLORREF accent = RGB(10, 107, 132);

double thread_cpu() {
    FILETIME created, exited, kernel, user;
    if (!GetThreadTimes(GetCurrentThread(), &created, &exited, &kernel, &user))
        throw std::runtime_error("No se pudo medir el tiempo de CPU");
    auto ticks = [](FILETIME time) {
        return (std::uint64_t(time.dwHighDateTime) << 32) | time.dwLowDateTime;
    };
    return (ticks(kernel) + ticks(user)) / 10000000.0;
}

double elapsed(Clock::time_point start) {
    return std::chrono::duration<double>(Clock::now() - start).count();
}

std::wstring decimal(double value, int digits = 3) {
    std::wostringstream out;
    if (std::abs(value) >= 1e9) out << std::setprecision(7);
    else out << std::fixed << std::setprecision(digits);
    out << value;
    return out.str();
}

std::wstring wide(const char* message) {
    const int length = MultiByteToWideChar(CP_UTF8, 0, message, -1, nullptr, 0);
    if (!length) return L"Error durante la operación";
    std::wstring result(length, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, message, -1, result.data(), length);
    result.pop_back();
    return result;
}

struct Snapshot {
    Cost initial = 0, best = 0, evaluations = 0;
    Sequence order;
    double cpu = 0, wall = 0;
    bool done = false, cancelled = false;
    std::wstring error;
};

struct Sample {
    double cpu, fmed;
};

struct App {
    HWND window{}, heading{}, preset{}, filename{}, open{}, optimize{}, matrix_title{}, ordered{}, matrix{};
    HWND chart_title{}, chart{}, progress{}, status{}, result_title{}, sequence_label{}, sequence{};
    std::array<HWND, 4> labels{}, values{};
    HBRUSH backdrop = CreateSolidBrush(background);
    HFONT normal{}, title{}, section{}, number{};
    int dpi = 96;
    bool closing = false;
    Instance instance;
    Snapshot displayed, shared;
    std::vector<Sample> samples;
    std::mutex updates;
    std::jthread worker;

    ~App() {
        worker.request_stop();
        if (worker.joinable()) worker.join();
        for (auto font : {normal, title, section, number}) if (font) DeleteObject(font);
        DeleteObject(backdrop);
    }

    int px(int value) const { return MulDiv(value, dpi, 96); }

    HWND control(const wchar_t* type, const wchar_t* caption, DWORD style = 0, int id = 0, DWORD extended = 0) {
        return CreateWindowExW(extended, type, caption, WS_CHILD | WS_VISIBLE | style, 0, 0, 0, 0,
                               window, reinterpret_cast<HMENU>(INT_PTR(id)), GetModuleHandleW(nullptr), nullptr);
    }

    void fonts() {
        auto font = [&](int size, int weight) {
            return CreateFontW(-px(size), 0, 0, 0, weight, FALSE, FALSE, FALSE, DEFAULT_CHARSET,
                               OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH, L"Segoe UI");
        };
        const auto old = {normal, title, section, number};
        normal = font(14, FW_NORMAL);
        title = font(30, FW_SEMIBOLD);
        section = font(17, FW_SEMIBOLD);
        number = font(23, FW_SEMIBOLD);
        for (auto item : {preset, filename, open, optimize, ordered, matrix, status, sequence_label, sequence})
            SendMessageW(item, WM_SETFONT, WPARAM(normal), TRUE);
        for (auto item : labels) SendMessageW(item, WM_SETFONT, WPARAM(normal), TRUE);
        for (auto item : values) SendMessageW(item, WM_SETFONT, WPARAM(number), TRUE);
        for (auto item : {matrix_title, chart_title, result_title}) SendMessageW(item, WM_SETFONT, WPARAM(section), TRUE);
        SendMessageW(heading, WM_SETFONT, WPARAM(title), TRUE);
        for (auto previous : old) if (previous) DeleteObject(previous);
        column_widths();
    }

    bool create() {
        dpi = GetDpiForWindow(window);
        heading = control(L"STATIC", L"OptContest A2");
        preset = control(L"STATIC", L"Iterated Greedy r400 · 57 s de CPU");
        filename = control(L"STATIC", L"Abre una instancia TXT para empezar", SS_ENDELLIPSIS);
        open = control(L"BUTTON", L"Abrir TXT…", WS_TABSTOP | BS_PUSHBUTTON, open_id);
        optimize = control(L"BUTTON", L"Optimizar", WS_TABSTOP | BS_DEFPUSHBUTTON, optimize_id);
        matrix_title = control(L"STATIC", L"Matriz de tiempos");
        ordered = control(L"BUTTON", L"Ver en la mejor secuencia", WS_TABSTOP | BS_AUTOCHECKBOX, ordered_id);
        matrix = control(WC_LISTVIEWW, L"", WS_TABSTOP | LVS_REPORT | LVS_OWNERDATA | LVS_SHOWSELALWAYS,
                         0, WS_EX_CLIENTEDGE);
        chart_title = control(L"STATIC", L"Evolución del mejor Fmed");
        chart = control(L"STATIC", L"Gráfico de Fmed por tiempo de CPU", SS_OWNERDRAW | WS_BORDER, chart_id);
        progress = control(PROGRESS_CLASSW, L"", PBS_SMOOTH);
        status = control(L"STATIC", L"Esperando una instancia");
        result_title = control(L"STATIC", L"Resultado");
        const wchar_t* captions[] = {L"Fmed inicial", L"Mejor Fmed", L"CPU de cálculo (s)", L"Tiempo total (s)"};
        for (std::size_t i = 0; i < labels.size(); ++i) {
            labels[i] = control(L"STATIC", captions[i]);
            values[i] = control(L"STATIC", L"—", SS_ENDELLIPSIS);
        }
        sequence_label = control(L"STATIC", L"Mejor secuencia");
        sequence = control(L"EDIT", L"", WS_TABSTOP | WS_VSCROLL | ES_MULTILINE | ES_READONLY | ES_AUTOVSCROLL,
                           0, WS_EX_CLIENTEDGE);
        if (!matrix || !chart || !progress || !sequence || !open || !optimize) return false;
        ListView_SetExtendedListViewStyle(matrix, LVS_EX_FULLROWSELECT | LVS_EX_GRIDLINES | LVS_EX_DOUBLEBUFFER);
        ListView_SetUnicodeFormat(matrix, TRUE);
        add_column(0, L"Orden");
        SendMessageW(progress, PBM_SETRANGE32, 0, 1000);
        EnableWindow(optimize, FALSE);
        EnableWindow(ordered, FALSE);
        fonts();
        return SetTimer(window, 1, 160, nullptr) != 0;
    }

    void layout() {
        RECT rect{};
        GetClientRect(window, &rect);
        const int width = rect.right, height = rect.bottom;
        if (!matrix || !width || !height) return;
        const int margin = px(22), gap = px(20), right = width - margin;
        const int content = width - 2 * margin, button = px(119);
        const int lower_height = std::clamp(height * 39 / 100, px(244), px(350));
        const int lower = height - margin - lower_height;
        const int result_width = std::max(px(325), content * 35 / 100);
        const int result_left = right - result_width, chart_width = result_left - margin - gap;
        auto place = [](HWND item, int x, int y, int w, int h) {
            MoveWindow(item, x, y, std::max(0, w), std::max(0, h), TRUE);
        };
        place(heading, margin, px(16), content - 2 * button - gap, px(39));
        place(preset, margin, px(57), content, px(22));
        place(open, right - 2 * button - px(10), px(22), button, px(34));
        place(optimize, right - button, px(22), button, px(34));
        place(filename, margin, px(85), content, px(23));
        place(matrix_title, margin, px(115), px(240), px(24));
        place(ordered, right - px(229), px(112), px(229), px(27));
        place(matrix, margin, px(145), content, lower - px(145) - gap);
        place(chart_title, margin, lower, chart_width, px(26));
        place(chart, margin, lower + px(30), chart_width, lower_height - px(74));
        place(status, margin, height - margin - px(39), chart_width, px(20));
        place(progress, margin, height - margin - px(12), chart_width, px(12));
        place(result_title, result_left, lower, result_width, px(26));
        for (int i = 0; i < 4; ++i) {
            const int x = result_left + (i % 2) * (result_width / 2);
            const int y = lower + px(33 + (i / 2) * 57);
            place(labels[i], x, y, result_width / 2 - px(6), px(20));
            place(values[i], x, y + px(19), result_width / 2 - px(6), px(32));
        }
        place(sequence_label, result_left, lower + px(151), result_width, px(21));
        place(sequence, result_left, lower + px(175), result_width, lower_height - px(175));
    }

    void add_column(int index, std::wstring name) {
        LVCOLUMNW column{};
        column.mask = LVCF_TEXT | LVCF_WIDTH | LVCF_FMT;
        column.pszText = name.data();
        column.cx = px(index ? 62 : 77);
        column.fmt = index ? LVCFMT_RIGHT : LVCFMT_LEFT;
        ListView_InsertColumn(matrix, index, &column);
    }

    void column_widths() {
        if (!matrix) return;
        ListView_SetColumnWidth(matrix, 0, px(77));
        if (instance.durations.empty()) return;
        const auto largest = *std::max_element(instance.durations.begin(), instance.durations.end());
        const int width = px(std::max(62, int(std::to_wstring(largest).size()) * 10 + 18));
        for (int col = 1; col <= instance.machines; ++col) ListView_SetColumnWidth(matrix, col, width);
    }

    void clear_result() {
        displayed = {};
        shared = {};
        samples.clear();
        for (auto value : values) SetWindowTextW(value, L"—");
        SetWindowTextW(sequence, L"");
        SendMessageW(ordered, BM_SETCHECK, BST_UNCHECKED, 0);
        EnableWindow(ordered, FALSE);
        SendMessageW(progress, PBM_SETPOS, 0, 0);
        InvalidateRect(chart, nullptr, FALSE);
        InvalidateRect(matrix, nullptr, FALSE);
    }

    void load() {
        std::array<wchar_t, 32768> path{};
        OPENFILENAMEW dialog{};
        dialog.lStructSize = sizeof(dialog);
        dialog.hwndOwner = window;
        dialog.lpstrFilter = L"Instancias TXT (*.txt)\0*.txt\0Todos los archivos\0*.*\0";
        dialog.lpstrFile = path.data();
        dialog.nMaxFile = DWORD(path.size());
        dialog.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR | OFN_EXPLORER;
        if (!GetOpenFileNameW(&dialog)) {
            if (CommDlgExtendedError()) MessageBoxW(window, L"No se pudo abrir el selector de archivos", L"OptContest", MB_ICONERROR);
            return;
        }
        try {
            const std::filesystem::path selected(path.data());
            std::ifstream file(selected, std::ios::binary);
            auto loaded = read_instance(file);
            clear_result();
            SendMessageW(matrix, WM_SETREDRAW, FALSE, 0);
            ListView_SetItemCount(matrix, 0);
            for (int col = Header_GetItemCount(ListView_GetHeader(matrix)) - 1; col > 0; --col)
                ListView_DeleteColumn(matrix, col);
            instance = std::move(loaded);
            for (int machine = 0; machine < instance.machines; ++machine)
                add_column(machine + 1, L"M" + std::to_wstring(machine));
            column_widths();
            ListView_SetItemCount(matrix, instance.jobs);
            SendMessageW(matrix, WM_SETREDRAW, TRUE, 0);
            InvalidateRect(matrix, nullptr, TRUE);
            const auto caption = selected.filename().wstring() + L"   ·   " + std::to_wstring(instance.jobs)
                + L" órdenes × " + std::to_wstring(instance.machines) + L" máquinas";
            SetWindowTextW(filename, caption.c_str());
            SetWindowTextW(status, L"Lista para optimizar");
            EnableWindow(optimize, TRUE);
            SetFocus(optimize);
        } catch (const std::exception& error) {
            MessageBoxW(window, wide(error.what()).c_str(), L"Instancia incompatible", MB_ICONERROR);
        }
    }

    void cell(NMLVDISPINFOW& info) {
        auto& item = info.item;
        if (!(item.mask & LVIF_TEXT) || !item.pszText || item.cchTextMax <= 0
            || item.iItem < 0 || item.iItem >= instance.jobs || item.iSubItem < 0 || item.iSubItem > instance.machines) return;
        const bool reordered = !displayed.order.empty() && SendMessageW(ordered, BM_GETCHECK, 0, 0) == BST_CHECKED;
        const int job = reordered ? displayed.order[item.iItem] : item.iItem;
        const auto value = item.iSubItem ? instance.durations[job * instance.machines + item.iSubItem - 1] : job + 1;
        lstrcpynW(item.pszText, std::to_wstring(value).c_str(), item.cchTextMax);
    }

    void publish(Snapshot result) {
        std::scoped_lock lock(updates);
        shared = std::move(result);
    }

    struct RunContext {
        App& app;
        std::stop_token stop;
        Clock::time_point start;
        double cpu_start, next_sample = 0;

        Snapshot snapshot(const Search& search) const {
            Snapshot result;
            result.initial = search.initial_cost;
            result.best = search.best_cost;
            result.evaluations = search.evaluations;
            result.order = search.best;
            result.cpu = thread_cpu() - cpu_start;
            result.wall = elapsed(start);
            return result;
        }
    };

    static bool check_budget(const Search& search, void* data) {
        auto& run = *static_cast<RunContext*>(data);
        if (run.stop.stop_requested()) return true;
        const double used = thread_cpu() - run.cpu_start;
        if (used >= run.next_sample) {
            run.app.publish(run.snapshot(search));
            run.next_sample = used + 0.2;
        }
        return used >= search.cpu_limit;
    }

    void optimize_or_cancel() {
        if (worker.joinable()) {
            worker.request_stop();
            EnableWindow(optimize, FALSE);
            SetWindowTextW(status, L"Cancelando…");
            return;
        }
        if (!instance.jobs) return;
        const auto start = Clock::now();
        clear_result();
        try {
            worker = std::jthread([this, start](std::stop_token stop) {
                Snapshot result;
                try {
                    RunContext context{*this, stop, start, thread_cpu()};
                    std::random_device entropy;
                    const std::uint64_t seed = (std::uint64_t(entropy()) << 32) ^ entropy();
                    Search search(instance.jobs, instance.machines, instance.durations, seed, cpu_budget, std::numeric_limits<Cost>::max());
                    search.budget_reached = check_budget;
                    search.budget_context = &context;
                    ig_search<6, 100, 400>(search);
                    result = context.snapshot(search);
                } catch (const std::exception& error) {
                    result.error = wide(error.what());
                }
                result.cancelled = stop.stop_requested();
                result.done = true;
                publish(std::move(result));
            });
            EnableWindow(open, FALSE);
            SetWindowTextW(optimize, L"Cancelar");
            SetWindowTextW(status, L"Buscando…");
        } catch (const std::exception& error) {
            MessageBoxW(window, wide(error.what()).c_str(), L"No se pudo iniciar la búsqueda", MB_ICONERROR);
        }
    }

    void update() {
        if (!worker.joinable()) return;
        Snapshot next;
        {
            std::scoped_lock lock(updates);
            next = shared;
        }
        if (!next.order.empty()) {
            const bool changed = next.order != displayed.order;
            const double fmed = double(next.best) / instance.jobs;
            SetWindowTextW(values[0], decimal(double(next.initial) / instance.jobs).c_str());
            SetWindowTextW(values[1], decimal(fmed).c_str());
            SetWindowTextW(values[2], decimal(next.cpu).c_str());
            SetWindowTextW(values[3], decimal(next.wall).c_str());
            if (samples.empty() || samples.back().cpu != next.cpu || samples.back().fmed != fmed) {
                samples.push_back({next.cpu, fmed});
                InvalidateRect(chart, nullptr, FALSE);
            }
            const int budget_used = int(std::clamp(next.cpu / cpu_budget, 0.0, 1.0) * 1000);
            SendMessageW(progress, PBM_SETPOS, budget_used, 0);
            displayed = std::move(next);
            if (changed) {
                std::wostringstream text;
                for (std::size_t i = 0; i < displayed.order.size(); ++i) {
                    if (i) text << L' ';
                    text << displayed.order[i] + 1;
                }
                SetWindowTextW(sequence, text.str().c_str());
                EnableWindow(ordered, TRUE);
                InvalidateRect(matrix, nullptr, FALSE);
            }
        } else if (next.done) {
            displayed = std::move(next);
        } else {
            return;
        }
        if (!displayed.done) return;
        worker.join();
        if (closing) {
            DestroyWindow(window);
            return;
        }
        EnableWindow(open, TRUE);
        EnableWindow(optimize, TRUE);
        SetWindowTextW(optimize, L"Optimizar");
        if (!displayed.error.empty()) {
            SetWindowTextW(status, L"Búsqueda interrumpida");
            MessageBoxW(window, displayed.error.c_str(), L"Error de búsqueda", MB_ICONERROR);
        } else {
            const auto text = std::wstring(displayed.cancelled ? L"Cancelada" : L"Completada") + L"   ·   "
                + std::to_wstring(displayed.evaluations) + L" evaluaciones";
            SetWindowTextW(status, text.c_str());
        }
    }

    void plot(const DRAWITEMSTRUCT& draw) {
        const HDC dc = draw.hDC;
        RECT area = draw.rcItem;
        FillRect(dc, &area, GetSysColorBrush(COLOR_WINDOW));
        const auto old_font = SelectObject(dc, normal);
        SetBkMode(dc, TRANSPARENT);
        SetTextColor(dc, ink);
        if (samples.empty()) {
            DrawTextW(dc, L"Inicia la búsqueda para ver la evolución del Fmed", -1, &area, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
            SelectObject(dc, old_font);
            return;
        }
        const int left = area.left + px(82), right = area.right - px(19);
        const int top = area.top + px(11), bottom = area.bottom - px(37);
        if (right <= left || bottom <= top) {
            SelectObject(dc, old_font);
            return;
        }
        const double highest = samples.front().fmed, lowest = samples.back().fmed;
        const double padding = std::max({0.01, (highest - lowest) * 0.08, highest * 1e-9});
        const double top_value = highest + padding, bottom_value = std::max(0.0, lowest - padding);
        const double end = std::max(0.1, samples.back().cpu);
        const HPEN grid = CreatePen(PS_SOLID, 1, RGB(221, 228, 235));
        const auto old_pen = SelectObject(dc, grid);
        for (int i = 0; i <= 3; ++i) {
            const int y = top + (bottom - top) * i / 3;
            MoveToEx(dc, left, y, nullptr);
            LineTo(dc, right, y);
            const auto label = decimal(top_value - (top_value - bottom_value) * i / 3, 2);
            RECT axis{area.left + px(3), y - px(9), left - px(7), y + px(9)};
            DrawTextW(dc, label.c_str(), -1, &axis, DT_RIGHT | DT_VCENTER | DT_SINGLELINE);
        }
        for (int i = 0; i <= 2; ++i) {
            const int x = left + (right - left) * i / 2;
            const auto label = decimal(end * i / 2, 1);
            RECT axis{x - px(30), bottom + px(4), x + px(14), bottom + px(21)};
            DrawTextW(dc, label.c_str(), -1, &axis, i == 0 ? DT_RIGHT : DT_CENTER);
        }
        RECT axis{left, bottom + px(19), right, area.bottom};
        DrawTextW(dc, L"CPU de cálculo (s)", -1, &axis, DT_CENTER | DT_SINGLELINE);
        const HPEN line = CreatePen(PS_SOLID, px(2), accent);
        SelectObject(dc, line);
        int previous_y = 0;
        for (std::size_t i = 0; i < samples.size(); ++i) {
            const auto& point = samples[i];
            const int x = left + int((right - left) * point.cpu / end);
            const int y = bottom - int((bottom - top) * (point.fmed - bottom_value) / (top_value - bottom_value));
            if (!i) MoveToEx(dc, left, y, nullptr);
            else LineTo(dc, x, previous_y);
            LineTo(dc, x, y);
            previous_y = y;
        }
        SelectObject(dc, old_pen);
        SelectObject(dc, old_font);
        DeleteObject(grid);
        DeleteObject(line);
    }

    LRESULT message(UINT kind, WPARAM wparam, LPARAM lparam) {
        switch (kind) {
        case WM_CREATE: return create() ? 0 : -1;
        case WM_SIZE: layout(); return 0;
        case WM_DPICHANGED: {
            dpi = HIWORD(wparam);
            fonts();
            const auto& rect = *reinterpret_cast<RECT*>(lparam);
            SetWindowPos(window, nullptr, rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top, SWP_NOZORDER);
            return 0;
        }
        case WM_GETMINMAXINFO: {
            auto& limits = *reinterpret_cast<MINMAXINFO*>(lparam);
            limits.ptMinTrackSize = {px(800), px(575)};
            return 0;
        }
        case WM_COMMAND:
            if (HIWORD(wparam) == BN_CLICKED) {
                switch (LOWORD(wparam)) {
                case open_id: if (!worker.joinable()) load(); return 0;
                case optimize_id: optimize_or_cancel(); return 0;
                case ordered_id: InvalidateRect(matrix, nullptr, FALSE); return 0;
                }
            }
            break;
        case WM_NOTIFY: {
            auto& notice = *reinterpret_cast<NMHDR*>(lparam);
            if (notice.hwndFrom == matrix && notice.code == LVN_GETDISPINFOW)
                cell(*reinterpret_cast<NMLVDISPINFOW*>(lparam));
            break;
        }
        case WM_DRAWITEM:
            if (wparam == chart_id) { plot(*reinterpret_cast<DRAWITEMSTRUCT*>(lparam)); return TRUE; }
            break;
        case WM_CTLCOLORSTATIC:
            if (reinterpret_cast<HWND>(lparam) != sequence) {
                SetTextColor(reinterpret_cast<HDC>(wparam), ink);
                SetBkColor(reinterpret_cast<HDC>(wparam), background);
                return reinterpret_cast<LRESULT>(backdrop);
            }
            break;
        case WM_ERASEBKGND: {
            RECT rect{};
            GetClientRect(window, &rect);
            FillRect(reinterpret_cast<HDC>(wparam), &rect, backdrop);
            return TRUE;
        }
        case WM_TIMER: if (wparam == 1) update(); return 0;
        case WM_CLOSE:
            if (worker.joinable()) {
                closing = true;
                worker.request_stop();
                return 0;
            }
            DestroyWindow(window);
            return 0;
        case WM_DESTROY: KillTimer(window, 1); PostQuitMessage(0); return 0;
        }
        return DefWindowProcW(window, kind, wparam, lparam);
    }
};

LRESULT CALLBACK window_proc(HWND window, UINT kind, WPARAM wparam, LPARAM lparam) {
    if (kind == WM_NCCREATE) {
        auto& args = *reinterpret_cast<CREATESTRUCTW*>(lparam);
        auto* app = static_cast<App*>(args.lpCreateParams);
        app->window = window;
        SetWindowLongPtrW(window, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(app));
    }
    auto* app = reinterpret_cast<App*>(GetWindowLongPtrW(window, GWLP_USERDATA));
    return app ? app->message(kind, wparam, lparam) : DefWindowProcW(window, kind, wparam, lparam);
}
}

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE, PWSTR, int show) {
    INITCOMMONCONTROLSEX controls{sizeof(controls), ICC_LISTVIEW_CLASSES | ICC_PROGRESS_CLASS};
    if (!InitCommonControlsEx(&controls)) return 1;
    WNDCLASSW window_class{};
    window_class.lpfnWndProc = window_proc;
    window_class.hInstance = instance;
    window_class.hIcon = LoadIconW(nullptr, IDI_APPLICATION);
    window_class.hCursor = LoadCursorW(nullptr, IDC_ARROW);
    window_class.lpszClassName = L"OptContestWindow";
    if (!RegisterClassW(&window_class)) return 1;
    App app;
    const int dpi = GetDpiForSystem();
    RECT work{};
    SystemParametersInfoW(SPI_GETWORKAREA, 0, &work, 0);
    const int width = std::min<int>(MulDiv(1260, dpi, 96), work.right - work.left);
    const int height = std::min<int>(MulDiv(815, dpi, 96), work.bottom - work.top);
    HWND window = CreateWindowExW(0, window_class.lpszClassName, L"OptContest A2", WS_OVERLAPPEDWINDOW,
                                  work.left + (work.right - work.left - width) / 2,
                                  work.top + (work.bottom - work.top - height) / 2, width, height,
                                  nullptr, nullptr, instance, &app);
    if (!window) return 1;
    ShowWindow(window, show);
    MSG message{};
    while (GetMessageW(&message, nullptr, 0, 0) > 0) {
        if (!IsDialogMessageW(window, &message)) {
            TranslateMessage(&message);
            DispatchMessageW(&message);
        }
    }
    return int(message.wParam);
}
