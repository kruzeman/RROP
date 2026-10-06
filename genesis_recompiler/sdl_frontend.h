/* SDL2 presents the existing RGB renderer and supplies three-button pad input. */
#ifndef GENESIS_SDL_FRONTEND_H
#define GENESIS_SDL_FRONTEND_H
#ifdef GENESIS_SDL2
#include <SDL.h>
#include "rings_window.h"
#include "rings_camera.h"
#include "rings_mouse.h"
#include "rings_settings_state.h"
#ifdef GENESIS_RINGS_MENU_FONT
#include "rings_font_sdl.h"
#endif

typedef struct {
    CPU *console; /* Borrowed only for immutable ROM reads on the shadow CPU. */
    SDL_Window *window;
#ifdef GENESIS_RINGS_SAVES
    RingsSaves *saves;
    RingsSettings settings;
    uint8_t startup_held,startup_latched,startup_armed,startup_injected,startup_previous,startup_focused;
#endif
#ifdef GENESIS_RINGS_MENU_FONT
    RingsFont font;
#endif
    SDL_Renderer *renderer;
    SDL_Texture *texture;
    SDL_AudioDeviceID audio_device;
    int audio_running;
    unsigned width, height;
    uint64_t last_frame, next_service, origin_master;
    Uint64 origin_counter, frequency;
    int paused, stopped, fast_forward, no_throttle, error;
    int wide_window;
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
    RingsCameraTween camera;
    int spill_x,spill_y,last_smooth;
    int native_actor_x,native_actor_y;
    uint8_t *native_pixels;
    uint8_t *hero_pixels,*motion_lift;
    uint64_t actor_frame;
    int actor_scene;
#endif
#ifdef GENESIS_RINGS_WIDE
    RingsMouse mouse;
    unsigned zoom_percent,last_zoom;
    uint8_t *zoom_pixels;
    SDL_Texture *zoom_world,*zoom_ui,*zoom_spill,*zoom_guard;
    unsigned zoom_width,zoom_height;
#endif
} SDLHost;
#include "rings_startup_sdl.h"
#ifdef GENESIS_RINGS_WIDE
static unsigned sdl_host_scene_percent(const SDLHost *h,const VDP *v) {
    return v->native_scene ? 100:h->zoom_percent;
}
#endif

static void sdl_host_close(SDLHost *h) {
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
    free(h->native_pixels);h->native_pixels=NULL;
    free(h->hero_pixels);h->hero_pixels=NULL;
    free(h->motion_lift);h->motion_lift=NULL;
#endif
#ifdef GENESIS_RINGS_SAVES
    SDL_DestroyTexture(h->settings.paper_texture);
#endif
#ifdef GENESIS_RINGS_WIDE
    free(h->zoom_pixels);h->zoom_pixels=NULL;
    SDL_DestroyTexture(h->zoom_world);h->zoom_world=NULL;
    SDL_DestroyTexture(h->zoom_ui);h->zoom_ui=NULL;
    SDL_DestroyTexture(h->zoom_spill);h->zoom_spill=NULL;
    SDL_DestroyTexture(h->zoom_guard);h->zoom_guard=NULL;
#endif
    if(h->audio_device)SDL_CloseAudioDevice(h->audio_device);
    h->audio_device=0;h->audio_running=0;
    SDL_DestroyTexture(h->texture);
#ifdef GENESIS_RINGS_MENU_FONT
    rings_font_close(&h->font);
#endif
    SDL_DestroyRenderer(h->renderer);
    SDL_DestroyWindow(h->window);
    h->texture=NULL; h->renderer=NULL; h->window=NULL;
    SDL_Quit();
}
static int sdl_host_error(SDLHost *h, const char *operation) {
    fprintf(stderr,"SDL2 %s: %s\n",operation,SDL_GetError());
    h->error=1; return 0;
}
static int sdl_host_open(SDLHost *h) {
#ifdef GENESIS_RINGS_WIDE
    if(!h->zoom_percent)h->zoom_percent=100;
#endif
    if (SDL_Init(SDL_INIT_VIDEO|SDL_INIT_EVENTS)) return sdl_host_error(h,"initialization failed");
    SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY,"nearest");
    h->window=SDL_CreateWindow("RROP",SDL_WINDOWPOS_CENTERED,SDL_WINDOWPOS_CENTERED,
        h->wide_window ? 1200:960,672,SDL_WINDOW_RESIZABLE|SDL_WINDOW_ALLOW_HIGHDPI);
    if (!h->window) return sdl_host_error(h,"window creation failed");
    h->renderer=SDL_CreateRenderer(h->window,-1,SDL_RENDERER_ACCELERATED);
    if (!h->renderer) h->renderer=SDL_CreateRenderer(h->window,-1,SDL_RENDERER_SOFTWARE);
    if (!h->renderer) return sdl_host_error(h,"renderer creation failed");
    SDL_SetRenderDrawColor(h->renderer,0,0,0,255);
    if (SDL_RenderClear(h->renderer)) return sdl_host_error(h,"clear failed");
    SDL_RenderPresent(h->renderer);
    h->frequency=SDL_GetPerformanceFrequency(); h->origin_counter=SDL_GetPerformanceCounter();
    return 1;
}
static void sdl_host_audio_open(SDLHost *h,CPU *c) {
    if(SDL_InitSubSystem(SDL_INIT_AUDIO)) {
        fprintf(stderr,"SDL2 audio unavailable: %s; video continues\n",SDL_GetError());return;
    }
    SDL_AudioSpec desired={0},obtained={0};
    desired.freq=AUDIO_RATE;desired.format=AUDIO_S16SYS;desired.channels=2;desired.samples=512;
    h->audio_device=SDL_OpenAudioDevice(NULL,0,&desired,&obtained,0);
    if(!h->audio_device) {
        fprintf(stderr,"SDL2 audio device unavailable: %s; video continues\n",SDL_GetError());return;
    }
    c->audio.playback=1;
}
static int sdl_host_audio_service(SDLHost *h,CPU *c) {
    if(!h->audio_device)return 1;
    int playing=!h->paused && !h->stopped && !c->fault && !h->fast_forward && !h->no_throttle;
#ifdef GENESIS_RINGS_SAVES
    playing=playing && (!h->saves || !h->saves->menu) && !h->settings.menu;
#endif
    c->audio.playback=playing;
    if(!playing) {
        SDL_PauseAudioDevice(h->audio_device,1);SDL_ClearQueuedAudio(h->audio_device);
        h->audio_running=0;c->audio.read=0;c->audio.count=0;return 1;
    }
    // Bound latency even when a host cannot keep up. Never change chip clocks.
    Uint32 queued=SDL_GetQueuedAudioSize(h->audio_device);
    if(queued>AUDIO_RATE*4/10){
        c->audio.dropped+=queued/4;SDL_ClearQueuedAudio(h->audio_device);h->audio_running=0;
    }
    int16_t buffer[1024*2];unsigned count;
    while((count=audio_pop(c,buffer,1024))!=0) {
        if(SDL_QueueAudio(h->audio_device,buffer,count*4))return sdl_host_error(h,"audio queue failed");
    }
    // A small preroll keeps the first callback from immediately underrunning.
    if(!h->audio_running && SDL_GetQueuedAudioSize(h->audio_device)>=AUDIO_RATE*4/50) {
        SDL_PauseAudioDevice(h->audio_device,0);h->audio_running=1;
    }
    return 1;
}
static uint8_t sdl_pad_key(SDL_Keycode key) {
    switch (key) {
        case SDLK_UP: return PAD_UP; case SDLK_DOWN: return PAD_DOWN;
        case SDLK_LEFT: return PAD_LEFT; case SDLK_RIGHT: return PAD_RIGHT;
        case SDLK_z: return PAD_A; case SDLK_x: return PAD_B; case SDLK_c: return PAD_C;
        case SDLK_RETURN: return PAD_START;
        default: return 0;
    }
}
#include "rings_mouse_sdl.h"
static void sdl_host_rebase(SDLHost *h, const CPU *c) {
    h->origin_counter=SDL_GetPerformanceCounter(); h->origin_master=c->master_cycles;
}
#include "rings_saves_sdl.h"
#include "rings_settings_sdl.h"
#ifdef GENESIS_RINGS_WIDE
/* Keep the original scene pixels until SDL maps them to drawable pixels.
   The UI mask is a separate native-resolution layer, never zoomed. */
static int sdl_host_spill_upload(SDLHost *h,const VDP *v) {
    int dx=0,dy=0;
    const uint8_t *scene=v->zoom_scene,*lift=v->zoom_lift;
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
    dx=rings_camera_round(h->camera.x);dy=rings_camera_round(h->camera.y);
    h->spill_x=dx;h->spill_y=dy;
    if(h->actor_scene && h->actor_frame==v->rendered_frames) {
        scene=h->native_pixels;
        lift=h->motion_lift;
    }
#endif
    for(unsigned y=0;y<RINGS_ZOOM_HEIGHT;++y)for(unsigned x=0;x<RINGS_ZOOM_WIDTH;++x) {
        unsigned p=y*RINGS_ZOOM_WIDTH+x,ink=scene[p];uint8_t *out=h->zoom_pixels+p*4;
        memcpy(out,v->zoom_palette+ink*3,3);
        int accepted=0;
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
        /* The native traversal has already selected the accepted cells.
           Do not clip their roofs, trees or actors a second time by their
           pixel ground projection; flat floor still stays behind the UI. */
        accepted=h->actor_scene && !rings_view_wide(v) &&
                 sdl_host_scene_percent(h,v)==100 && v->native_motion.valid;
#endif
        out[3]=(accepted ? ink && lift[p]:
            rings_zoom_spill_layer(v,scene,lift,(int)x,(int)y,sdl_host_scene_percent(h,v),dx,dy)) ? 255:0;
    }
    return SDL_UpdateTexture(h->zoom_spill,NULL,h->zoom_pixels,RINGS_ZOOM_WIDTH*4) ? sdl_host_error(h,"zoom elevated upload failed"):1;
}
static int sdl_host_zoom_upload(SDLHost *h,CPU *c,const VDP *v,const uint8_t *base) {
    const uint8_t *scene=v->zoom_scene;
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
    h->actor_scene=0;h->actor_frame=v->rendered_frames;
    h->native_actor_x=rings_camera_round(h->camera.hero_x);h->native_actor_y=rings_camera_round(h->camera.hero_y);
    if(!rings_view_wide(v) && sdl_host_scene_percent(h,v)==100 && v->native_motion.valid) {
        if(!h->native_pixels)h->native_pixels=malloc(RINGS_ZOOM_WIDTH*RINGS_ZOOM_HEIGHT);
        if(!h->motion_lift)h->motion_lift=malloc(RINGS_ZOOM_WIDTH*RINGS_ZOOM_HEIGHT);
        if(!h->native_pixels || !h->motion_lift)return sdl_host_error(h,"native motion allocation failed");
        if(!rings_native_pixels(c,v,h->native_actor_x,h->native_actor_y,h->native_pixels,h->motion_lift))
            return sdl_host_error(h,"native motion resource rendering failed");
        scene=h->native_pixels;h->actor_scene=1;
    } else if(h->camera.enabled && v->hero_patch.valid &&
              (h->native_actor_x || h->native_actor_y || h->camera.hero_active)) {
        if(!h->native_pixels)h->native_pixels=malloc(RINGS_ZOOM_WIDTH*RINGS_ZOOM_HEIGHT);
        if(!h->motion_lift)h->motion_lift=malloc(RINGS_ZOOM_WIDTH*RINGS_ZOOM_HEIGHT);
        if(!h->hero_pixels)h->hero_pixels=malloc(RINGS_HERO_WIDTH*RINGS_HERO_HEIGHT*2);
        if(!h->native_pixels || !h->motion_lift || !h->hero_pixels)return sdl_host_error(h,"outdoor motion allocation failed");
        uint8_t *patch_lift=h->hero_pixels+RINGS_HERO_WIDTH*RINGS_HERO_HEIGHT;
        if(!rings_hero_pixels(c,v,h->native_actor_x,h->native_actor_y,h->hero_pixels,patch_lift))
            return sdl_host_error(h,"outdoor motion resource rendering failed");
        memcpy(h->native_pixels,v->zoom_scene,RINGS_ZOOM_WIDTH*RINGS_ZOOM_HEIGHT);
        memcpy(h->motion_lift,v->zoom_lift,RINGS_ZOOM_WIDTH*RINGS_ZOOM_HEIGHT);
        /* Scenery, actors and ground ownership share the same overwritten
           region: the old hero and its former spill outline disappear. */
        unsigned left=RINGS_ZOOM_LEFT+40+RINGS_HERO_LEFT,top=RINGS_ZOOM_TOP+RINGS_HERO_TOP;
        for(unsigned y=0;y<RINGS_HERO_HEIGHT;++y) {
            unsigned dst=(top+y)*RINGS_ZOOM_WIDTH+left,src=y*RINGS_HERO_WIDTH;
            memcpy(h->native_pixels+dst,h->hero_pixels+src,RINGS_HERO_WIDTH);
            memcpy(h->motion_lift+dst,patch_lift+src,RINGS_HERO_WIDTH);
        }
        scene=h->native_pixels;h->actor_scene=1;
    }
#else
    (void)c;
#endif
    if(!h->zoom_pixels)h->zoom_pixels=malloc(RINGS_ZOOM_WIDTH*RINGS_ZOOM_HEIGHT*4);
    if(!h->zoom_pixels)return sdl_host_error(h,"zoom buffer allocation failed");
    if(!h->zoom_world) {
        h->zoom_world=SDL_CreateTexture(h->renderer,SDL_PIXELFORMAT_RGBA32,SDL_TEXTUREACCESS_STREAMING,
                                        RINGS_ZOOM_WIDTH,RINGS_ZOOM_HEIGHT);
        if(!h->zoom_world || SDL_SetTextureBlendMode(h->zoom_world,SDL_BLENDMODE_BLEND))
            return sdl_host_error(h,"zoom scene texture creation failed");
    }
    if(!h->zoom_ui || h->zoom_width!=h->width || h->zoom_height!=h->height) {
        SDL_DestroyTexture(h->zoom_ui);
        SDL_DestroyTexture(h->zoom_guard);h->zoom_guard=NULL;
        h->zoom_ui=SDL_CreateTexture(h->renderer,SDL_PIXELFORMAT_RGBA32,SDL_TEXTUREACCESS_STREAMING,h->width,h->height);
        if(!h->zoom_ui || SDL_SetTextureBlendMode(h->zoom_ui,SDL_BLENDMODE_BLEND))
            return sdl_host_error(h,"zoom interface texture creation failed");
        h->zoom_width=h->width;h->zoom_height=h->height;
    }
    for(unsigned p=0;p<h->width*h->height;++p)
        memcpy(h->zoom_pixels+p*3,v->zoom_restore[p] ? v->zoom_background+p*3:base+p*3,3);
    if(SDL_UpdateTexture(h->texture,NULL,h->zoom_pixels,h->width*3))return sdl_host_error(h,"zoom background upload failed");
    for(unsigned p=0;p<RINGS_ZOOM_WIDTH*RINGS_ZOOM_HEIGHT;++p) {
        unsigned ink=scene[p];uint8_t *out=h->zoom_pixels+p*4;
        memcpy(out,v->zoom_palette+ink*3,3);out[3]=ink ? 255:0;
    }
    if(SDL_UpdateTexture(h->zoom_world,NULL,h->zoom_pixels,RINGS_ZOOM_WIDTH*4))return sdl_host_error(h,"zoom scene upload failed");
    for(unsigned p=0;p<h->width*h->height;++p) {
        memcpy(h->zoom_pixels+p*4,v->zoom_restore[p] ? v->zoom_background+p*3:base+p*3,3);
        h->zoom_pixels[p*4+3]=v->zoom_mask[p] ? 0:255;
    }
    if(SDL_UpdateTexture(h->zoom_ui,NULL,h->zoom_pixels,h->width*4))return sdl_host_error(h,"zoom interface upload failed");
    if(rings_view_wide(v))return 1;
    if(!h->zoom_spill) {
        h->zoom_spill=SDL_CreateTexture(h->renderer,SDL_PIXELFORMAT_RGBA32,SDL_TEXTUREACCESS_STREAMING,
                                      RINGS_ZOOM_WIDTH,RINGS_ZOOM_HEIGHT);
        if(!h->zoom_spill || SDL_SetTextureBlendMode(h->zoom_spill,SDL_BLENDMODE_BLEND))
            return sdl_host_error(h,"zoom elevated texture creation failed");
    }
    if(!h->zoom_guard) {
        h->zoom_guard=SDL_CreateTexture(h->renderer,SDL_PIXELFORMAT_RGBA32,SDL_TEXTUREACCESS_STREAMING,h->width,h->height);
        if(!h->zoom_guard || SDL_SetTextureBlendMode(h->zoom_guard,SDL_BLENDMODE_BLEND))
            return sdl_host_error(h,"zoom foreground texture creation failed");
    }
    if(!sdl_host_spill_upload(h,v))return 0;
    for(unsigned p=0;p<h->width*h->height;++p) {
        memcpy(h->zoom_pixels+p*4,base+p*3,3);
        h->zoom_pixels[p*4+3]=v->zoom_restore[p] ? 0:255;
    }
    return SDL_UpdateTexture(h->zoom_guard,NULL,h->zoom_pixels,h->width*4) ? sdl_host_error(h,"zoom foreground upload failed"):1;
}
static int sdl_host_zoom_draw(SDLHost *h,const VDP *v) {
    int width,height;
    if(SDL_GetRendererOutputSize(h->renderer,&width,&height) || SDL_RenderSetLogicalSize(h->renderer,0,0) ||
       SDL_RenderSetScale(h->renderer,1,1) || SDL_RenderSetViewport(h->renderer,NULL))return sdl_host_error(h,"zoom viewport failed");
    if(width<=0 || height<=0)return 1;
    double camera_x=0,camera_y=0;
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
    camera_x=h->camera.x;camera_y=h->camera.y;
#endif
    unsigned percent=sdl_host_scene_percent(h,v);
    RingsWindowLayout canvas=rings_window_layout(v,width,height,percent,camera_x,camera_y);
    double scale=canvas.world_scale;
    SDL_Rect viewport={0,0,(int)(h->width*scale+0.5),(int)(h->height*scale+0.5)};
    viewport.x=(int)(canvas.world_x+0.5);viewport.y=(int)(canvas.world_y+0.5);
    double zoom=percent/100.0;
    int target_x=(int)v->zoom_focus_x-RINGS_ZOOM_LEFT+16-(rings_view_wide(v) ? 0:40);
    int target_y=(int)v->zoom_focus_y-RINGS_ZOOM_TOP;
    double world_x=canvas.adaptive ? canvas.world_x:viewport.x;
    double world_y=canvas.adaptive ? canvas.world_y:viewport.y;
    SDL_FRect world={(float)(world_x+(target_x-v->zoom_focus_x*zoom)*scale),
                     (float)(world_y+(target_y-v->zoom_focus_y*zoom)*scale),
                     (float)(RINGS_ZOOM_WIDTH*zoom*scale),(float)(RINGS_ZOOM_HEIGHT*zoom*scale)};
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
    world.x+=(float)(h->camera.x*scale);world.y+=(float)(h->camera.y*scale);
    if(h->camera.active || h->camera.hero_active)++h->camera.motion_frames;
#endif
    if(canvas.adaptive) {
        SDL_SetRenderDrawColor(h->renderer,v->zoom_background[0],v->zoom_background[1],v->zoom_background[2],255);
        if(SDL_RenderClear(h->renderer) || SDL_RenderCopyF(h->renderer,h->zoom_world,NULL,&world))
            return sdl_host_error(h,"adaptive world presentation failed");
        for(unsigned i=0;i<3;++i) {
            RingsWindowBand band=rings_window_ui_band(&canvas,i);
            SDL_Rect source={band.x,band.y,band.w,band.h};
            double x,y;rings_window_ui_origin(&canvas,band.x,band.y,&x,&y);
            SDL_FRect to={(float)(x+band.x*canvas.scale),(float)(y+band.y*canvas.scale),
                          (float)(band.w*canvas.scale),(float)(band.h*canvas.scale)};
            if(SDL_RenderCopyF(h->renderer,h->zoom_ui,&source,&to))return sdl_host_error(h,"adaptive HUD presentation failed");
        }
        SDL_SetRenderDrawColor(h->renderer,0,0,0,255);
    } else if(SDL_RenderClear(h->renderer) || SDL_RenderCopy(h->renderer,h->texture,NULL,&viewport) ||
       SDL_RenderSetClipRect(h->renderer,&viewport) || SDL_RenderCopyF(h->renderer,h->zoom_world,NULL,&world) ||
       SDL_RenderSetClipRect(h->renderer,NULL) || SDL_RenderCopy(h->renderer,h->zoom_ui,NULL,&viewport))
        return sdl_host_error(h,"zoom presentation failed");
    if(!rings_view_wide(v) && (SDL_RenderSetClipRect(h->renderer,&viewport) ||
       SDL_RenderCopyF(h->renderer,h->zoom_spill,NULL,&world) || SDL_RenderSetClipRect(h->renderer,NULL) ||
       SDL_RenderCopy(h->renderer,h->zoom_guard,NULL,&viewport)))return sdl_host_error(h,"zoom elevated presentation failed");
#ifdef GENESIS_RINGS_MENU_FONT
    if(h->font.path && v->font_enabled) {
        SDL_Rect text_viewport=viewport;
        text_viewport.x+=(int)((h->width-v->frame_width)*0.5*scale+0.5);
        if(!rings_font_draw_view(&h->font,h->renderer,v,&text_viewport,canvas.adaptive ? canvas.scale:scale,&canvas))return sdl_host_error(h,"external font presentation failed");
    }
#endif
#ifdef GENESIS_RINGS_SAVES
    rings_save_overlay(h,v);rings_settings_overlay(h,v);
#endif
    SDL_RenderPresent(h->renderer);return 1;
}
#endif
static int sdl_host_draw(SDLHost *h, const VDP *v) {
    if (!v->rendered_frames) {
#ifdef GENESIS_RINGS_SAVES
        SDL_RenderClear(h->renderer);rings_save_overlay(h,v);rings_settings_overlay(h,v);SDL_RenderPresent(h->renderer);
#endif
        return 1;
    }
    unsigned presentation_width=v->frame_width;
#ifdef GENESIS_RINGS_WIDE
    if(rings_view_wide(v))presentation_width=RINGS_WIDE_WIDTH;
#endif
    int texture_changed=!h->texture || h->width!=presentation_width || h->height!=v->frame_height;
    if (texture_changed) {
        SDL_DestroyTexture(h->texture);
        h->texture=SDL_CreateTexture(h->renderer,SDL_PIXELFORMAT_RGB24,SDL_TEXTUREACCESS_STREAMING,
            presentation_width,v->frame_height);
        if (!h->texture) return sdl_host_error(h,"texture creation failed");
        h->width=presentation_width; h->height=v->frame_height;
        if (SDL_RenderSetLogicalSize(h->renderer,(int)h->width,(int)h->height))
            return sdl_host_error(h,"logical size failed");
    }
    int upload=texture_changed || h->last_frame!=v->rendered_frames;
#ifdef GENESIS_RINGS_WIDE
    int zoom_active=v->zoom_world_visible && (rings_view_wide(v) || (v->zoom_enabled && h->zoom_percent!=100));
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
    int motion=h->camera.active || h->camera.hero_active || h->camera.x || h->camera.y ||
               h->camera.hero_x || h->camera.hero_y;
    int motion_source=rings_view_wide(v) || h->zoom_percent!=100 || v->native_motion.valid;
    zoom_active|=h->camera.enabled && motion && motion_source && v->zoom_world_visible && v->camera.valid;
    int native_active=h->console && h->camera.enabled && v->native_scene && v->native_motion.valid && v->camera.valid;
    zoom_active|=native_active && motion;
    int actor_active=h->console && h->camera.enabled && (native_active || v->hero_patch.valid) && v->camera.valid;
    upload|=actor_active && (h->native_actor_x!=rings_camera_round(h->camera.hero_x) ||
                            h->native_actor_y!=rings_camera_round(h->camera.hero_y));
    upload|=h->last_smooth!=zoom_active;h->last_smooth=zoom_active;
#endif
    upload|=zoom_active && (!h->zoom_ui || h->zoom_width!=h->width || h->zoom_height!=h->height);
    upload|=h->last_zoom!=h->zoom_percent;
#endif
    if (upload) {
        const uint8_t *pixels=v->frame;
#ifdef GENESIS_RINGS_MENU_FONT
        if(h->font.path && v->font_enabled && v->font_count)pixels=v->font_frame;
#endif
#ifdef GENESIS_RINGS_WIDE
        if(rings_view_wide(v)) {
            pixels=v->wide_frame;
#ifdef GENESIS_RINGS_MENU_FONT
            if(h->font.path && v->font_enabled && v->font_count)pixels=v->wide_font_frame;
#endif
        }
        h->last_zoom=h->zoom_percent;
        if(zoom_active) {
            if(!sdl_host_zoom_upload(h,h->console,v,pixels))return 0;
        } else
#endif
        if (SDL_UpdateTexture(h->texture,NULL,pixels,presentation_width*3))
            return sdl_host_error(h,"texture upload failed");
        h->last_frame=v->rendered_frames;
    }
#ifdef GENESIS_RINGS_WIDE
    if(zoom_active) {
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
        if(!upload && !rings_view_wide(v) &&
           (h->spill_x!=rings_camera_round(h->camera.x) || h->spill_y!=rings_camera_round(h->camera.y)))
            if(!sdl_host_spill_upload(h,v))return 0;
#endif
        return sdl_host_zoom_draw(h,v);
    }
#endif
#ifdef GENESIS_RINGS_MENU_FONT
    if(h->font.path && v->font_enabled) {
        /* Disable the low-resolution logical transform: text uses device pixels. */
        int w,hg;
        if(SDL_GetRendererOutputSize(h->renderer,&w,&hg) || SDL_RenderSetLogicalSize(h->renderer,0,0) ||
           SDL_RenderSetScale(h->renderer,1,1) || SDL_RenderSetViewport(h->renderer,NULL))return sdl_host_error(h,"font viewport failed");
        if(w<=0 || hg<=0)return 1;
        double scale=(double)w/h->width;
        if((double)hg/h->height<scale)scale=(double)hg/h->height;
        SDL_Rect viewport={0,0,(int)(h->width*scale+0.5),(int)(h->height*scale+0.5)};
        viewport.x=(w-viewport.w)/2; viewport.y=(hg-viewport.h)/2;
        SDL_Rect text_viewport=viewport;
        text_viewport.x+=(int)((presentation_width-v->frame_width)*0.5*scale+0.5);
        if(SDL_RenderClear(h->renderer) || SDL_RenderCopy(h->renderer,h->texture,NULL,&viewport) ||
           !rings_font_draw(&h->font,h->renderer,v,&text_viewport,scale))return sdl_host_error(h,"external font presentation failed");
#ifdef GENESIS_RINGS_SAVES
        rings_save_overlay(h,v);rings_settings_overlay(h,v);
#endif
        SDL_RenderPresent(h->renderer); return 1;
    }
#endif
    if (SDL_RenderSetLogicalSize(h->renderer,(int)h->width,(int)h->height) ||
        SDL_RenderClear(h->renderer) || SDL_RenderCopy(h->renderer,h->texture,NULL,NULL))
        return sdl_host_error(h,"presentation failed");
#ifdef GENESIS_RINGS_SAVES
    rings_save_overlay(h,v);rings_settings_overlay(h,v);
#endif
    SDL_RenderPresent(h->renderer); return 1;
}
static void sdl_host_stop(SDLHost *h, const CPU *c) {
    if (h->stopped) return;
    h->stopped=1;
    char title[256];
    if (c->fault) {
        snprintf(title,sizeof title,"RROP - stopped: %s",c->reason);
        fprintf(stderr,"execution stopped at %06" PRIx32 ": %s\n",c->fault_address,c->reason);
    } else snprintf(title,sizeof title,"RROP - CPU halted (open Settings to exit)");
    SDL_SetWindowTitle(h->window,title);
}
static int sdl_host_service(SDLHost *h, CPU *c) {
    h->console=c;
    int redraw=0;
    SDL_Event event;
    while (SDL_PollEvent(&event)) {
        if (event.type==SDL_QUIT) return 0;
#ifdef GENESIS_RINGS_SAVES
        rings_startup_event(h,&event);
#endif
#ifdef GENESIS_RINGS_SAVES
        if(rings_settings_event(h,c,&event)) {redraw=1;continue;}
#endif
#ifdef GENESIS_RINGS_WIDE
        rings_mouse_event(h,c,&event);
#endif
#ifdef GENESIS_RINGS_SAVES
        if(rings_save_event(h,c,&event)) {redraw=1;continue;}
#endif
#ifdef GENESIS_RINGS_WIDE
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
        if(event.type==SDL_KEYDOWN && !event.key.repeat && event.key.keysym.sym==SDLK_F6 && c->vdp.zoom_enabled) {
            h->camera.enabled=!h->camera.enabled;rings_camera_reset(&h->camera);redraw=1;
#ifdef GENESIS_RINGS_SAVES
            h->settings.smooth=h->camera.enabled;rings_settings_write(h);
#endif
            fprintf(stderr,"smooth camera %s\n",h->camera.enabled ? "on":"off");continue;
        }
#endif
        if(c->vdp.zoom_enabled && !h->stopped
#ifdef GENESIS_RINGS_SAVES
            && (!h->settings.ready || (h->settings.enhanced && h->settings.zoom))
#endif
        ) {
            if(event.type==SDL_MOUSEWHEEL && c->vdp.zoom_world_visible) {
                int delta=event.wheel.y;
                if(delta>20)delta=20;
                if(delta<-20)delta=-20;
                if(event.wheel.direction==SDL_MOUSEWHEEL_FLIPPED)delta=-delta;
                if(delta) {
                    int percent=(int)h->zoom_percent+delta*10;
                    if(percent<50)percent=50;
                    if(percent>100)percent=100;
                    h->zoom_percent=(unsigned)percent;redraw=1;
#ifdef GENESIS_RINGS_SAVES
                    h->settings.saved_zoom=h->zoom_percent;
#endif
                }
            }
            if((event.type==SDL_MOUSEBUTTONDOWN && event.button.button==SDL_BUTTON_MIDDLE) ||
               (event.type==SDL_KEYDOWN && !event.key.repeat && event.key.keysym.sym==SDLK_0)) {
                h->zoom_percent=100;redraw=1;
#ifdef GENESIS_RINGS_SAVES
                h->settings.saved_zoom=100;
#endif
            }
        }
#endif
        if (event.type==SDL_WINDOWEVENT) {
            if (event.window.event==SDL_WINDOWEVENT_CLOSE) return 0;
            if (event.window.event==SDL_WINDOWEVENT_FOCUS_LOST) {
                c->pad_buttons[0]=0; h->fast_forward=0; sdl_host_rebase(h,c);
            }
            if (event.window.event==SDL_WINDOWEVENT_EXPOSED || event.window.event==SDL_WINDOWEVENT_SIZE_CHANGED)
                redraw=1;
        }
        if (event.type==SDL_KEYDOWN || event.type==SDL_KEYUP) {
            int down=event.type==SDL_KEYDOWN;
            SDL_Keycode key=event.key.keysym.sym;
            if (down && key==SDLK_ESCAPE) {
#ifdef GENESIS_RINGS_SAVES
                if(h->settings.ready) {
                    if(!event.key.repeat)rings_settings_open(h,c);
                    redraw=1;continue;
                }
#endif
                return 0;
            }
            uint8_t button=sdl_pad_key(key);
            if (down) c->pad_buttons[0]|=button; else c->pad_buttons[0]&=(uint8_t)~button;
            if (key==SDLK_TAB) { h->fast_forward=down; sdl_host_rebase(h,c); }
            if (down && !event.key.repeat && key==SDLK_SPACE && !h->stopped) {
                h->paused=!h->paused; sdl_host_rebase(h,c);
                SDL_SetWindowTitle(h->window,h->paused ? "RROP - paused":"RROP");
            }
        }
    }
#ifdef GENESIS_RINGS_SAVES
    rings_startup_keyboard(h);
    if(h->saves) {
        uint64_t previous_notice=h->saves->notice_until;
        rings_save_tick(h->saves,c,rings_save_now(h),!h->paused && !h->stopped && !c->fault && !h->saves->menu && !h->settings.menu);
        redraw|=h->saves->menu || h->saves->notice_until!=previous_notice;
        if(h->saves->notice_until && rings_save_now(h)>=h->saves->notice_until) {h->saves->notice_until=0;redraw=1;}
    }
#endif
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
    rings_camera_update(&h->camera,&c->vdp,c->master_cycles,vdp_master_frequency(&c->vdp),h->zoom_percent);
#endif
#ifdef GENESIS_RINGS_WIDE
    rings_mouse_update(h,c);
#endif
    if (redraw || h->last_frame!=c->vdp.rendered_frames)
        if (!sdl_host_draw(h,&c->vdp)) return 0;
    if(!sdl_host_audio_service(h,c))return 0;
    /* Service input every ~1 ms of modeled console time, even before video is enabled.
       Throttling uses emulated clocks, never changing the CPU/device scheduling. */
    h->next_service=c->master_cycles+vdp_master_frequency(&c->vdp)/1000;
    if (!h->paused && !h->stopped && !h->fast_forward && !h->no_throttle
#ifdef GENESIS_RINGS_SAVES
        && (!h->saves || !h->saves->menu) && !h->settings.menu
#endif
    ) {
        double simulated_ms=(double)(c->master_cycles-h->origin_master)*1000.0/vdp_master_frequency(&c->vdp);
        double elapsed_ms=(double)(SDL_GetPerformanceCounter()-h->origin_counter)*1000.0/(double)h->frequency;
        double ahead=simulated_ms-elapsed_ms;
        if (ahead>=1.0) SDL_Delay((Uint32)(ahead>10.0 ? 10.0:ahead));
    }
    return 1;
}
#endif
#endif
