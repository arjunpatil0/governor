// Probe for the "fresh exe runs its body twice" investigation (journal 0036/0037): appends one line "pid,parent_pid,qpc_s,image" to the file given as argv[1], then exits.
// Two lines with different pids = two real processes ran the body (the body runs exactly once per process).
#include <windows.h>
#include <tlhelp32.h>
#include <cstdio>

#ifndef PROBE_ID
#define PROBE_ID 0
#endif
static const int kProbeId = PROBE_ID;                 // changes the binary bytes per build (new hash)

static DWORD parent_pid() {
    HANDLE s = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    PROCESSENTRY32 e; e.dwSize = sizeof e; DWORD me = GetCurrentProcessId(), pp = 0;
    if (Process32First(s, &e)) do { if (e.th32ProcessID == me) { pp = e.th32ParentProcessID; break; } } while (Process32Next(s, &e));
    CloseHandle(s);
    return pp;
}

int main(int argc, char **argv) {
    if (argc < 2 || kProbeId < 0) return 2;
    LARGE_INTEGER f, c; QueryPerformanceFrequency(&f); QueryPerformanceCounter(&c);
    char img[MAX_PATH]; GetModuleFileNameA(nullptr, img, MAX_PATH);
    FILE *o = fopen(argv[1], "a");
    if (!o) return 3;
    fprintf(o, "%lu,%lu,%.6f,%s\n", GetCurrentProcessId(), parent_pid(), (double)c.QuadPart / (double)f.QuadPart, img);
    fclose(o);
    Sleep(200);
    return 0;
}
