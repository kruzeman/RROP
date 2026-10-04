/* Lossless external resources. CPU execution still uses translated operations. */
#ifndef GENESIS_RESOURCES_H
#define GENESIS_RESOURCES_H
#ifdef __linux__
#include <unistd.h>
#elif defined(__APPLE__)
#include <mach-o/dyld.h>
#endif

typedef struct { size_t address, offset, size; } ResourceSpan;
typedef struct {
    const char *path;
    size_t size;
    uint32_t crc;
    const ResourceSpan *spans;
    size_t span_count;
} ROMResource;
static uint32_t resource_crc32(const uint8_t *data,size_t size) {
    uint32_t crc=UINT32_MAX;
    for(size_t i=0;i<size;++i){
        crc^=data[i];
        for(unsigned j=0;j<8;++j)crc=(crc>>1)^(0xedb88320u&(0u-(crc&1)));
    }
    return crc^UINT32_MAX;
}
static uint8_t *resource_load(const char *directory,size_t rom_size,
    const uint8_t *code,const ResourceSpan *code_spans,size_t code_count,
    const ROMResource *resources,size_t resource_count) {
    uint8_t *rom=(uint8_t *)calloc(rom_size,1);
    if(!rom){fprintf(stderr,"cannot allocate ROM resource map\n");return NULL;}
    for(size_t i=0;i<code_count;++i){
        const ResourceSpan *s=&code_spans[i];memcpy(rom+s->address,code+s->offset,s->size);
    }
    for(size_t i=0;i<resource_count;++i){
        const ROMResource *r=&resources[i];
        size_t length=strlen(directory)+strlen(r->path)+2;
        char *path=(char *)malloc(length);
        uint8_t *data=(uint8_t *)malloc(r->size);
        if(!path || !data){free(path);free(data);free(rom);fprintf(stderr,"cannot allocate resource buffer\n");return NULL;}
        snprintf(path,length,"%s/%s",directory,r->path);
        FILE *file=fopen(path,"rb");
        if(!file){fprintf(stderr,"cannot open resource %s: %s\n",path,strerror(errno));free(path);free(data);free(rom);return NULL;}
        int valid=fread(data,1,r->size,file)==r->size;
        if(valid)valid=fgetc(file)==EOF && !ferror(file);
        if(fclose(file))valid=0;
        if(!valid || resource_crc32(data,r->size)!=r->crc){
            fprintf(stderr,"resource size/checksum mismatch: %s\n",path);free(path);free(data);free(rom);return NULL;
        }
        for(size_t j=0;j<r->span_count;++j){
            const ResourceSpan *s=&r->spans[j];memcpy(rom+s->address,data+s->offset,s->size);
        }
        free(path);free(data);
    }
    return rom;
}
#ifndef GENESIS_NO_MAIN
static char *resource_default_directory(const char *argv0,const char *relative) {
    char executable[4096];const char *name=argv0;
#ifdef __linux__
    ssize_t n=readlink("/proc/self/exe",executable,sizeof executable-1);
    if(n>0 && (size_t)n<sizeof executable-1){executable[n]=0;name=executable;}
#elif defined(__APPLE__)
    uint32_t size=sizeof executable;
    char *resolved=NULL;
    if(!_NSGetExecutablePath(executable,&size)) {
        resolved=realpath(executable,NULL);name=resolved ? resolved:executable;
    }
#else
    (void)executable;
#endif
    const char *slash=strrchr(name,'/');size_t prefix=slash ? (size_t)(slash-name)+1:0;
    char *directory=(char *)malloc(prefix+strlen(relative)+1);
    if(directory){memcpy(directory,name,prefix);strcpy(directory+prefix,relative);}
#ifdef __APPLE__
    free(resolved);
#endif
    return directory;
}
static int resource_main(int argc,char **argv,const char *relative,size_t rom_size,
    const uint8_t *code,const ResourceSpan *code_spans,size_t code_count,
    const ROMResource *resources,size_t resource_count,int cartridge) {
    const char *directory=NULL;
    for(int i=1;i<argc;++i)if(!strcmp(argv[i],"--resources-dir")){
        if(i+1==argc || !argv[i+1][0]){fprintf(stderr,"--resources-dir requires a directory\n");return 64;}
        directory=argv[++i];
    } else if(!strcmp(argv[i],"--limit") || !strcmp(argv[i],"--peek") ||
        !strcmp(argv[i],"--audio") || !strcmp(argv[i],"--region") ||
        !strcmp(argv[i],"--dump-audio") || !strcmp(argv[i],"--dump-frame") ||
        !strcmp(argv[i],"--dump-vram") || !strcmp(argv[i],"--dump-z80")) {
        if(i+1<argc)++i;
    }
    char *owned=NULL;
    if(!directory){owned=resource_default_directory(argv[0],relative);directory=owned;}
    if(!directory){fprintf(stderr,"cannot allocate resource directory\n");return 1;}
    uint8_t *rom=resource_load(directory,rom_size,code,code_spans,code_count,resources,resource_count);
    free(owned);if(!rom)return 1;
    int result=run_main(argc,argv,rom,rom_size,cartridge);
    free(rom);return result;
}
#endif
#endif
