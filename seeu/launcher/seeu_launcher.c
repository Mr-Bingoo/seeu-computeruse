// SeeU 小程序(10-31):让 AI 客户端通过它拉起 SeeU 的 MCP 服务,辅助功能 / 屏幕录制授权记在「SeeU」上。
// 起因:Claude 聊天页等客户端用 disclaimer 直接拉起 Python,授权就要给 Python 本身(谁拉起 Python 都白拿)。
// 本程序当"负责进程",普通方式 spawn 子进程 → 子进程的授权算在 SeeU 头上。
// 🔴 不收任何参数,只跑同目录上一层的 mcp_server.py,防别人借它跑别的程序蹭权限。
#include <libgen.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <signal.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>

extern char **environ;
static pid_t child = 0;

static void fwd(int sig) { if (child > 0) kill(child, sig); }

int main(void) {
    char raw[PATH_MAX], exe[PATH_MAX], dir[PATH_MAX], server[PATH_MAX];
    uint32_t n = sizeof(raw);
    if (_NSGetExecutablePath(raw, &n) != 0 || !realpath(raw, exe)) { fprintf(stderr, "SeeU: 找不到自己的位置\n"); return 1; }
    // exe = …/seeu/launcher/SeeU.app/Contents/MacOS/SeeU → 往上 5 层到 seeu/
    strcpy(dir, exe);
    for (int i = 0; i < 5; i++) strcpy(dir, dirname(dir));
    snprintf(server, sizeof(server), "%s/mcp_server.py", dir);
    char *argv[] = {"/usr/bin/python3", server, NULL};
    signal(SIGTERM, fwd); signal(SIGINT, fwd); signal(SIGHUP, fwd);
    if (posix_spawn(&child, argv[0], NULL, NULL, argv, environ) != 0) { perror("SeeU: 启动 Python 失败"); return 1; }
    int st = 0;
    while (waitpid(child, &st, 0) < 0) {}
    return WIFEXITED(st) ? WEXITSTATUS(st) : 1;
}
