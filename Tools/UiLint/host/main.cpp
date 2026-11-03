// wowlua: a native host for the client's own Lua 5.1 (Engine/Source/lua-5.1/src), used by Tools/UiLint.
//
//   wowlua -p file.lua...        parse only (same parser the client runs); exit 1 on the first syntax error
//   wowlua -g file.lua...        list global reads and writes as "file:line:GET|SET:name" (from the bytecode)
//   wowlua script.lua [args...]  run a script with the libraries the game opens (base, string, table, math,
//                                bit; see FrameScript_Initialize) plus a few host-only helpers for tests:
//                                print, host_loadfile, host_readfile, host_date, host_time, host_clock,
//                                host_traceback, host_exit
//
// The game itself has no print, io, os, debug or package; the helpers exist only in this host.

extern "C++" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
#include "lobject.h"
#include "lopcodes.h"
#include "lstate.h"
}
#include <cstdio>
#include <cstdlib>
#include <cstring>

static int host_print(lua_State* L) {
    int n = lua_gettop(L);
    for (int i = 1; i <= n; i++) {
        lua_getglobal(L, "tostring");
        lua_pushvalue(L, i);
        lua_call(L, 1, 1);
        const char* s = lua_tostring(L, -1);
        fputs(s ? s : "?", stdout);
        lua_pop(L, 1);
        if (i < n) fputc('\t', stdout);
    }
    fputc('\n', stdout);
    fflush(stdout);
    return 0;
}

static int host_readfile(lua_State* L) {
    FILE* f = fopen(luaL_checkstring(L, 1), "rb");
    if (!f) {
        lua_pushnil(L);
        return 1;
    }
    luaL_Buffer b;
    luaL_buffinit(L, &b);
    char buf[4096];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0) luaL_addlstring(&b, buf, n);
    fclose(f);
    luaL_pushresult(&b);
    return 1;
}

// host_loadfile(path [, chunkname]) -> function | nil, message
static int host_loadfile(lua_State* L) {
    const char* path = luaL_checkstring(L, 1);
    const char* chunk = luaL_optstring(L, 2, path);
    FILE* f = fopen(path, "rb");
    if (!f) {
        lua_pushnil(L);
        lua_pushfstring(L, "cannot open %s", path);
        return 2;
    }
    luaL_Buffer b;
    luaL_buffinit(L, &b);
    char buf[4096];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0) luaL_addlstring(&b, buf, n);
    fclose(f);
    luaL_pushresult(&b);
    size_t len;
    const char* src = lua_tolstring(L, -1, &len);
    // Skip a UTF-8 BOM like FrameXML does.
    if (len >= 3 && (unsigned char)src[0] == 0xEF && (unsigned char)src[1] == 0xBB && (unsigned char)src[2] == 0xBF) {
        src += 3;
        len -= 3;
    }
    lua_pushfstring(L, "@%s", chunk);
    if (luaL_loadbuffer(L, src, len, lua_tostring(L, -1))) {
        lua_pushnil(L);
        lua_insert(L, -2);
        return 2;
    }
    return 1;
}

static int host_exit(lua_State* L) {
    fflush(stdout);
    exit(static_cast<int>(luaL_optinteger(L, 1, 0)));
    return 0;
}

static void list_globals(const char* file, const Proto* p) {
    for (int pc = 0; pc < p->sizecode; pc++) {
        Instruction i = p->code[pc];
        OpCode op = GET_OPCODE(i);
        if (op == OP_GETGLOBAL || op == OP_SETGLOBAL) {
            const TValue* k = &p->k[GETARG_Bx(i)];
            if (ttisstring(k)) {
                int line = (p->lineinfo && pc < p->sizelineinfo) ? p->lineinfo[pc] : 0;
                printf("%s:%d:%s:%s\n", file, line, op == OP_GETGLOBAL ? "GET" : "SET", svalue(k));
            }
        }
    }
    for (int j = 0; j < p->sizep; j++) list_globals(file, p->p[j]);
}

static void open_client_libs(lua_State* L) {
    // Same set as FrameScript_Initialize (Engine/Source/FrameScript/FrameScript.cpp).
    lua_pushcfunction(L, luaopen_base);
    lua_pushstring(L, "");
    lua_call(L, 1, 0);
    lua_pushcfunction(L, luaopen_string);
    lua_pushstring(L, LUA_STRLIBNAME);
    lua_call(L, 1, 0);
    lua_pushcfunction(L, luaopen_table);
    lua_pushstring(L, LUA_TABLIBNAME);
    lua_call(L, 1, 0);
    lua_pushcfunction(L, luaopen_math);
    lua_pushstring(L, LUA_MATHLIBNAME);
    lua_call(L, 1, 0);
    lua_pushcfunction(L, luaopen_bit);
    lua_pushstring(L, "bit");
    lua_call(L, 1, 0);
}

static void open_host_helpers(lua_State* L) {
    // os.date / os.time / os.clock are exposed under host_* names only; the game has no os table.
    lua_pushcfunction(L, luaopen_os);
    lua_pushstring(L, LUA_OSLIBNAME);
    lua_call(L, 1, 0);
    lua_getglobal(L, "os");
    lua_getfield(L, -1, "date");
    lua_setglobal(L, "host_date");
    lua_getfield(L, -1, "time");
    lua_setglobal(L, "host_time");
    lua_getfield(L, -1, "clock");
    lua_setglobal(L, "host_clock");
    lua_pop(L, 1);
    lua_pushnil(L);
    lua_setglobal(L, "os");
    lua_pushcfunction(L, luaopen_debug);
    lua_pushstring(L, LUA_DBLIBNAME);
    lua_call(L, 1, 0);
    lua_getglobal(L, "debug");
    lua_getfield(L, -1, "traceback");
    lua_setglobal(L, "host_traceback");
    lua_pop(L, 1);
    lua_pushnil(L);
    lua_setglobal(L, "debug");
    lua_register(L, "print", host_print);
    lua_register(L, "host_readfile", host_readfile);
    lua_register(L, "host_loadfile", host_loadfile);
    lua_register(L, "host_exit", host_exit);
}

int main(int argc, char** argv) {
    lua_State* L = luaL_newstate();
    if (!L) {
        fprintf(stderr, "wowlua: cannot create state\n");
        return 2;
    }
    if (argc > 1 && (!strcmp(argv[1], "-p") || !strcmp(argv[1], "-g"))) {
        bool globals = !strcmp(argv[1], "-g");
        int rc = 0;
        for (int i = 2; i < argc; i++) {
            if (luaL_loadfile(L, argv[i])) {
                fprintf(stderr, "%s\n", lua_tostring(L, -1));
                lua_pop(L, 1);
                rc = 1;
                continue;
            }
            if (globals) {
                const Closure* cl = static_cast<const Closure*>(lua_topointer(L, -1));
                if (cl && !cl->c.isC) list_globals(argv[i], cl->l.p);
            }
            lua_pop(L, 1);
        }
        lua_close(L);
        return rc;
    }
    if (argc < 2) {
        fprintf(stderr, "usage: wowlua [-p|-g] file.lua...  |  wowlua script.lua [args...]\n");
        return 2;
    }
    open_client_libs(L);
    open_host_helpers(L);
    lua_newtable(L);
    for (int i = 2; i < argc; i++) {
        lua_pushstring(L, argv[i]);
        lua_rawseti(L, -2, i - 1);
    }
    lua_setglobal(L, "arg");
    lua_pushcfunction(L, host_loadfile);
    lua_pushstring(L, argv[1]);
    lua_call(L, 1, 2);
    if (lua_isnil(L, -2)) {
        fprintf(stderr, "%s\n", lua_tostring(L, -1));
        return 1;
    }
    lua_pop(L, 1);
    if (lua_pcall(L, 0, 0, 0)) {
        fprintf(stderr, "%s\n", lua_tostring(L, -1));
        return 1;
    }
    lua_close(L);
    return 0;
}
