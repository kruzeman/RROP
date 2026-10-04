/* Five manual slots and five rotating autosaves. Atomic file replacement.
   Host session/UI time is intentionally separate from the emulated machine. */
#ifndef GENESIS_RINGS_SAVES_H
#define GENESIS_RINGS_SAVES_H
#ifdef GENESIS_RINGS_SAVES
#include <sys/stat.h>
#include <fcntl.h>
#ifdef _WIN32
#include <windows.h>
#include <process.h>
#else
#include <unistd.h>
#endif
#include <time.h>
#include "save_state.h"
#include "rings_object_diagnostics_state.h"
enum { RINGS_SAVE_INTERVAL_MS=300000, RINGS_SAVE_SLOTS=10 };
typedef struct {int present,compatible;uint64_t timestamp,serial;unsigned game_time;} RingsSaveSlot;
typedef struct {
    RingsObjectDiagnostics objects;
    char directory[1024],message[256];
    RingsSaveSlot slots[RINGS_SAVE_SLOTS];
    uint64_t rom_hash,serial,elapsed_ms,last_ms,notice_until;
    unsigned temp_counter;
    int enabled,autosave,started,clock_ready,clock_active,menu,selected,loaded;
} RingsSaves;
static int rings_save_error(RingsSaves *s,const char *message) {
    snprintf(s->message,sizeof s->message,"%s",message);
    fprintf(stderr,"save: %s\n",message);return 0;
}
static int rings_save_path(const RingsSaves *s,int slot,char *path,size_t size) {
    int n=snprintf(path,size,"%s/%s-%d.grs",s->directory,slot<5 ? "manual":"auto",slot%5+1);
    return slot>=0 && slot<10 && n>=0 && (size_t)n<size;
}
#ifdef _WIN32
/* Host paths are UTF-8; use wide Win32 calls for Cyrillic user directories. */
static int rings_save_wide(const char *path,wchar_t *wide,int size) {
    return MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,path,-1,wide,size)>0;
}
static FILE *rings_save_read_file(const char *path) {
    wchar_t wide[1200];return rings_save_wide(path,wide,1200) ? _wfopen(wide,L"rb"):NULL;
}
#else
static FILE *rings_save_read_file(const char *path) {return fopen(path,"rb");}
#endif
static int rings_save_mkdir(const char *directory) {
    char path[1024];size_t size=strlen(directory);
    if(!size || size>=sizeof path)return 0;
    memcpy(path,directory,size+1);
#ifdef _WIN32
    for(size_t i=0;i<size;++i)if(path[i]=='\\')path[i]='/';
    size_t start=1;
    if(size>=3 && path[1]==':' && path[2]=='/')start=3;
    /* A UNC server/share is an existing root, not a directory to create. */
    if(size>=2 && path[0]=='/' && path[1]=='/') {
        start=2;for(int part=0;part<2;++part) {
            while(start<size && path[start]!='/')++start;
            if(start<size)++start;
        }
    }
    for(size_t i=start;i<=size;++i)if(path[i]=='/' || !path[i]) {
        char old=path[i];path[i]=0;wchar_t wide[1024];
        if(!rings_save_wide(path,wide,1024))return 0;
        if(!CreateDirectoryW(wide,NULL) && GetLastError()!=ERROR_ALREADY_EXISTS)return 0;
        DWORD attributes=GetFileAttributesW(wide);
        if(attributes==INVALID_FILE_ATTRIBUTES || !(attributes&FILE_ATTRIBUTE_DIRECTORY))return 0;
        path[i]=old;
    }
#else
    for(size_t i=1;i<=size;++i)if(path[i]=='/' || !path[i]) {
        char old=path[i];path[i]=0;
        if(mkdir(path,0700) && errno!=EEXIST)return 0;
        struct stat info;if(stat(path,&info) || !S_ISDIR(info.st_mode))return 0;
        path[i]=old;
    }
#endif
    return 1;
}
static int rings_save_header(const RingsSaves *s,const CPU *c,const uint8_t *h) {
    return !memcmp(h,"GRPSAVE1",8) && save_get(h+8,4)==1 &&
        save_get(h+12,4)<=SAVE_MAX_BYTES && save_get(h+20,4)==c->rom_size &&
        save_get(h+24,8)==s->rom_hash && save_get(h+52,4)==(unsigned)c->audio_mode &&
        save_get(h+60,4)==save_crc(h,60);
}
static void rings_save_scan(RingsSaves *s,const CPU *c) {
    for(int slot=0;slot<10;++slot) {
        RingsSaveSlot *m=&s->slots[slot];memset(m,0,sizeof *m);
        char path[1100];if(!rings_save_path(s,slot,path,sizeof path))continue;
        FILE *f=rings_save_read_file(path);if(!f)continue;
        m->present=1;uint8_t h[SAVE_HEADER_BYTES];
        if(fread(h,1,sizeof h,f)==sizeof h && rings_save_header(s,c,h)) {
            m->compatible=1;m->timestamp=save_get(h+32,8);m->serial=save_get(h+40,8);
            m->game_time=(unsigned)save_get(h+56,2);if(m->serial>s->serial)s->serial=m->serial;
        }
        fclose(f);
    }
}
static int rings_saves_open(RingsSaves *s,const CPU *c,const char *directory,int autosave) {
    memset(s,0,sizeof *s);s->rom_hash=save_rom_hash(c);s->autosave=autosave;
    int size;
    if(directory)size=snprintf(s->directory,sizeof s->directory,"%s",directory);
    else {
#ifdef _WIN32
        wchar_t local[1024];char utf8[1024];
        DWORD n=GetEnvironmentVariableW(L"LOCALAPPDATA",local,1024);
        if(!n || n>=1024 || !WideCharToMultiByte(CP_UTF8,0,local,-1,utf8,sizeof utf8,NULL,NULL))
            return rings_save_error(s,"set --save-dir (LOCALAPPDATA is unavailable or too long)");
        size=snprintf(s->directory,sizeof s->directory,"%s/GenesisRecomp/rings-of-power",utf8);
#else
        const char *state=getenv("XDG_STATE_HOME"),*home=getenv("HOME");
        if(state && state[0]=='/')size=snprintf(s->directory,sizeof s->directory,"%s/genesisrecomp/rings-of-power",state);
        else if(home && home[0]=='/')size=snprintf(s->directory,sizeof s->directory,"%s/.local/state/genesisrecomp/rings-of-power",home);
        else return rings_save_error(s,"set --save-dir (HOME and XDG_STATE_HOME are unavailable)");
#endif
    }
    if(size<=0 || (size_t)size>=sizeof s->directory)return rings_save_error(s,"save directory path is too long");
    if(!rings_save_mkdir(s->directory))return rings_save_error(s,"cannot create save directory");
    s->enabled=1;rings_save_scan(s,c);return 1;
}
#ifdef _WIN32
static int rings_save_write_all(HANDLE fd,const uint8_t *bytes,size_t size) {
    while(size) {
        DWORD n=0,count=size>MAXDWORD ? MAXDWORD:(DWORD)size;
        if(!WriteFile(fd,bytes,count,&n,NULL) || !n)return 0;
        bytes+=n;size-=n;
    }
    return 1;
}
#else
static int rings_save_write_all(int fd,const uint8_t *bytes,size_t size) {
    while(size) {
        ssize_t n=write(fd,bytes,size);
        if(n<0 && errno==EINTR)continue;
        if(n<=0)return 0;
        bytes+=n;size-=(size_t)n;
    }
    return 1;
}
#endif
static int rings_save_write_path(RingsSaves *s,CPU *c,const char *path,const char *label) {
    if(!s->enabled)return rings_save_error(s,"save directory unavailable");
    char temp[1200];
    SaveCodec out={0};int ok=save_encode(c,&out);
    if(!ok) {free(out.data);return rings_save_error(s,"cannot capture this machine state");}
    uint8_t h[SAVE_HEADER_BYTES]={0};memcpy(h,"GRPSAVE1",8);
    save_put(h+8,1,4);save_put(h+12,out.size,4);save_put(h+16,save_crc(out.data,out.size),4);
    save_put(h+20,c->rom_size,4);save_put(h+24,s->rom_hash,8);
    time_t timestamp=time(NULL);save_put(h+32,timestamp<0 ? 0:(uint64_t)timestamp,8);
    if(s->serial==UINT64_MAX) {free(out.data);return rings_save_error(s,"save sequence exhausted");}
    save_put(h+40,s->serial+1,8);save_put(h+52,(unsigned)c->audio_mode,4);
    save_put(h+56,(c->ram[0x0e16]<<8)|c->ram[0x0e17],2);
    save_put(h+60,save_crc(h,60),4);
#ifdef _WIN32
    snprintf(temp,sizeof temp,"%s.tmp.%ld.%u",path,(long)_getpid(),++s->temp_counter);
    wchar_t target[1200],temporary[1200];
    if(!rings_save_wide(path,target,1200) || !rings_save_wide(temp,temporary,1200)) {
        free(out.data);return rings_save_error(s,"invalid UTF-8 save path");
    }
    HANDLE fd=CreateFileW(temporary,GENERIC_WRITE,0,NULL,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,NULL);
    if(fd==INVALID_HANDLE_VALUE) {free(out.data);return rings_save_error(s,"cannot create save file");}
    ok=rings_save_write_all(fd,h,sizeof h) && rings_save_write_all(fd,out.data,out.size);
    if(ok && !FlushFileBuffers(fd))ok=0;
    if(!CloseHandle(fd))ok=0;
    /* Same-directory replacement keeps the previous slot on commit failure. */
    if(ok && !MoveFileExW(temporary,target,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH))ok=0;
    free(out.data);
    if(!ok) {DeleteFileW(temporary);return rings_save_error(s,"cannot commit save file; previous slot preserved");}
#else
    snprintf(temp,sizeof temp,"%s.tmp.%ld.%u",path,(long)getpid(),++s->temp_counter);
    int fd=open(temp,O_WRONLY|O_CREAT|O_EXCL,0600);
    if(fd<0) {free(out.data);return rings_save_error(s,"cannot create save file");}
    ok=rings_save_write_all(fd,h,sizeof h) && rings_save_write_all(fd,out.data,out.size);
    if(ok && fsync(fd))ok=0;
    if(close(fd))ok=0;
    if(ok && rename(temp,path))ok=0;
    free(out.data);
    if(!ok) {unlink(temp);return rings_save_error(s,"cannot commit save file; previous slot preserved");}
    /* The file has been committed. Directory sync improves crash durability. */
    fd=open(s->directory,O_RDONLY);if(fd>=0) {if(fsync(fd))fprintf(stderr,"save: directory sync unavailable\n");close(fd);}
#endif
    ++s->serial;rings_save_scan(s,c);
    snprintf(s->message,sizeof s->message,"%s saved",label);
    fprintf(stderr,"save: %s\n",s->message);return 1;
}
static int rings_save_write(RingsSaves *s,CPU *c,int slot) {
    char path[1100],label[32];
    if(!rings_save_path(s,slot,path,sizeof path))return rings_save_error(s,"invalid slot");
    snprintf(label,sizeof label,"%s %d",slot<5 ? "Manual":"Autosave",slot%5+1);
    return rings_save_write_path(s,c,path,label);
}
#include "rings_object_diagnostics.h"
static int rings_save_load(RingsSaves *s,CPU *c,int slot) {
    char path[1100];if(!s->enabled || !rings_save_path(s,slot,path,sizeof path))return rings_save_error(s,"invalid save slot");
    FILE *f=rings_save_read_file(path);if(!f)return rings_save_error(s,"slot is empty or cannot be opened");
    uint8_t h[SAVE_HEADER_BYTES];int ok=fread(h,1,sizeof h,f)==sizeof h;
    if(!ok || !rings_save_header(s,c,h) || save_get(h+60,4)!=save_crc(h,60)) {
        fclose(f);return rings_save_error(s,"incompatible or damaged save (check ROM and --audio mode)");
    }
    size_t size=(size_t)save_get(h+12,4);uint8_t *bytes=malloc(size ? size:1);
    ok=bytes && fread(bytes,1,size,f)==size && fgetc(f)==EOF && !ferror(f);
    if(fclose(f))ok=0;
    if(ok)ok=save_crc(bytes,size)==save_get(h+16,4);
    if(ok)ok=save_decode(c,bytes,size);
    free(bytes);
    if(!ok)return rings_save_error(s,"damaged save; current game is unchanged");
    memset(&s->objects,0,sizeof s->objects);
    s->started=1;s->elapsed_ms=0;s->clock_ready=0;s->loaded=1;
    snprintf(s->message,sizeof s->message,"%s %d loaded",slot<5 ? "Manual":"Autosave",slot%5+1);
    fprintf(stderr,"save: %s\n",s->message);return 1;
}
static int rings_save_slot_number(const char *name) {
    if(strlen(name)==8 && !strncmp(name,"manual-",7) && name[7]>='1' && name[7]<='5')return name[7]-'1';
    if(strlen(name)==6 && !strncmp(name,"auto-",5) && name[5]>='1' && name[5]<='5')return name[5]-'1'+5;
    return -1;
}
/* Wall time, not the game's accelerated clock. Do not count host pause/UI. */
static void rings_save_tick(RingsSaves *s,CPU *c,uint64_t now_ms,int active) {
    active=active && s->started && s->enabled && s->autosave;
    uint64_t elapsed=s->clock_ready && s->clock_active && active && now_ms>=s->last_ms ? now_ms-s->last_ms:0;
    s->last_ms=now_ms;s->clock_ready=1;s->clock_active=active;
    if(!active)return;
    s->elapsed_ms+=elapsed;
    if(s->elapsed_ms<RINGS_SAVE_INTERVAL_MS)return;
    s->elapsed_ms=0;int slot=5;
    for(int i=5;i<10;++i) {
        if(!s->slots[i].present) {slot=i;break;}
        if(s->slots[i].serial<s->slots[slot].serial)slot=i;
    }
    rings_save_write(s,c,slot);s->notice_until=now_ms+4000;
}
static void rings_save_input_clear(CPU *c) {
    memset(c->pad_buttons,0,sizeof c->pad_buttons);
    c->ram[0x18]=c->ram[0x19]=c->ram[0x1a]=c->ram[0x1b]=c->ram[0x2c]=c->ram[0xe14]=0;
}
static void rings_save_menu(RingsSaves *s,CPU *c,int mode) {
    if(mode==1 && (!s->started || c->fault)) {rings_save_error(s,"start a game before saving");return;}
    rings_save_scan(s,c);s->menu=mode;s->selected=0;s->message[0]=0;
    if(mode==2)for(int i=0;i<10;++i)
        if(s->slots[i].compatible && (!s->slots[s->selected].compatible || s->slots[i].serial>s->slots[s->selected].serial))s->selected=i;
    rings_save_input_clear(c);
}
/* Verified [!] ROM command dispatch sites. Skip only the old EEPROM call and
   its status message; leave the command's native stack/return path intact. */
static int rings_save_observe(RingsSaves *s,CPU *c,int window) {
    rings_objects_observe(s,c);
    if(c->pc==0xd28e || c->pc==0xd2be)s->started=1;
    if(c->pc==0xd284 || c->pc==0x15538) {s->started=0;s->elapsed_ms=0;}
    if(!window || c->fault || s->menu)return 0;
    if(c->pc==0x20670) {s->started=1;c->pc=0x2068a;rings_save_menu(s,c,1);return 1;}
    if(c->pc==0x20652) {c->pc=0x2066c;rings_save_menu(s,c,2);return 1;}
    if(c->pc==0x1b8ee) {c->pc=0x1b914;rings_save_menu(s,c,2);return 1;}
    return 0;
}
#endif
#endif
