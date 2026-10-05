/* Host slot chooser. A small built-in font works without SDL2_ttf. */
#ifndef GENESIS_RINGS_SAVES_SDL_H
#define GENESIS_RINGS_SAVES_SDL_H
#if defined(GENESIS_RINGS_SAVES) && defined(GENESIS_SDL2)
static const uint8_t rings_save_letters[36][5]={
 {0x3e,0x51,0x49,0x45,0x3e},{0,0x42,0x7f,0x40,0},{0x42,0x61,0x51,0x49,0x46},
 {0x21,0x41,0x45,0x4b,0x31},{0x18,0x14,0x12,0x7f,0x10},{0x27,0x45,0x45,0x45,0x39},
 {0x3c,0x4a,0x49,0x49,0x30},{1,0x71,9,5,3},{0x36,0x49,0x49,0x49,0x36},
 {6,0x49,0x49,0x29,0x1e},
 {0x7e,0x11,0x11,0x11,0x7e},{0x7f,0x49,0x49,0x49,0x36},{0x3e,0x41,0x41,0x41,0x22},
 {0x7f,0x41,0x41,0x22,0x1c},{0x7f,0x49,0x49,0x49,0x41},{0x7f,9,9,9,1},
 {0x3e,0x41,0x49,0x49,0x7a},{0x7f,8,8,8,0x7f},{0,0x41,0x7f,0x41,0},
 {0x20,0x40,0x41,0x3f,1},{0x7f,8,0x14,0x22,0x41},{0x7f,0x40,0x40,0x40,0x40},
 {0x7f,2,0x0c,2,0x7f},{0x7f,4,8,0x10,0x7f},{0x3e,0x41,0x41,0x41,0x3e},
 {0x7f,9,9,9,6},{0x3e,0x41,0x51,0x21,0x5e},{0x7f,9,0x19,0x29,0x46},
 {0x46,0x49,0x49,0x49,0x31},{1,1,0x7f,1,1},{0x3f,0x40,0x40,0x40,0x3f},
 {0x1f,0x20,0x40,0x20,0x1f},{0x3f,0x40,0x38,0x40,0x3f},{0x63,0x14,8,0x14,0x63},
 {7,8,0x70,8,7},{0x61,0x51,0x49,0x45,0x43}
};
static void rings_save_text(SDL_Renderer *r,int x,int y,int scale,const char *text,size_t max) {
    for(size_t n=0;text[n] && n<max;++n,x+=6*scale) {
        unsigned ch=(unsigned char)text[n];if(ch>='a' && ch<='z')ch-=32;
        const uint8_t *glyph=NULL;uint8_t punctuation[5]={0};
        if(ch>='0' && ch<='9')glyph=rings_save_letters[ch-'0'];
        else if(ch>='A' && ch<='Z')glyph=rings_save_letters[ch-'A'+10];
        else {
            if(ch=='-')memset(punctuation,8,5);
            if(ch==':')punctuation[2]=0x24;
            if(ch=='.')punctuation[2]=0x40;
            if(ch=='/') {punctuation[0]=0x20;punctuation[1]=0x10;punctuation[2]=8;punctuation[3]=4;punctuation[4]=2;}
            glyph=punctuation;
        }
        for(int col=0;col<5;++col)for(int row=0;row<7;++row)if(glyph[col]&(1<<row)) {
            SDL_Rect dot={x+col*scale,y+row*scale,scale,scale};SDL_RenderFillRect(r,&dot);
        }
    }
}
static uint64_t rings_save_now(const SDLHost *h) {
    return (uint64_t)((double)SDL_GetPerformanceCounter()*1000.0/(double)h->frequency);
}
/* Implemented by the shared Settings parchment renderer included below. */
static void rings_settings_paper(SDLHost *h,const VDP *v);
static void rings_settings_label(SDLHost *h,int x,int y,int scale,const char *label);
static void rings_settings_panel(SDLHost *h,SDL_Rect panel,int scale);
static void rings_save_overlay(SDLHost *h,const VDP *v) {
    RingsSaves *s=h->saves;if(!s)return;
    int notice=!s->menu && !h->settings.menu && s->message[0] && rings_save_now(h)<s->notice_until;
    if(!s->menu && !notice)return;
    int width,height;SDL_GetRendererOutputSize(h->renderer,&width,&height);
    if(width<=0 || height<=0)return;
    rings_settings_paper(h,v);
    SDL_RenderSetLogicalSize(h->renderer,0,0);SDL_RenderSetScale(h->renderer,1,1);
    SDL_RenderSetViewport(h->renderer,NULL);SDL_RenderSetClipRect(h->renderer,NULL);
    SDL_SetRenderDrawBlendMode(h->renderer,SDL_BLENDMODE_BLEND);
    int rows=s->menu==1 ? 5:10,native_height=notice ? 36:rows*24+72;
    int scale=width/384;if(height/(native_height+12)<scale)scale=height/(native_height+12);
    if(scale<1)scale=1;
    int panel_width=360*scale;if(panel_width>width-16)panel_width=width>16 ? width-16:width;
    SDL_Rect panel={(width-panel_width)/2,notice ? 8:(height-native_height*scale)/2,panel_width,native_height*scale};
    if(!notice) {
        SDL_SetRenderDrawColor(h->renderer,0,0,0,150);SDL_RenderFillRect(h->renderer,NULL);
    }
    rings_settings_panel(h,panel,scale);
    SDL_Rect text_clip={panel.x+16*scale,panel.y+8*scale,panel.w-32*scale,panel.h-12*scale};
    if(text_clip.w<1)text_clip.w=1;
    SDL_RenderSetClipRect(h->renderer,&text_clip);
    int x=panel.x+20*scale,y=panel.y+12*scale;
    if(notice)rings_settings_label(h,x,y,scale,s->message);
    else {
        rings_settings_label(h,x,y,scale,s->menu==1 ? "Save game - 5 manual slots":"Load game - Manual and autosaves");
        y+=22*scale;
        for(int i=0;i<rows;++i,y+=24*scale) {
            if(i==s->selected) {
                SDL_Rect row={panel.x+16*scale,y-2*scale,panel.w-32*scale,22*scale};
                SDL_SetRenderDrawColor(h->renderer,255,248,232,255);SDL_RenderFillRect(h->renderer,&row);
            }
            RingsSaveSlot *m=&s->slots[i];char label[64],detail[96],stamp[40]="Unknown date";
            snprintf(label,sizeof label,"%s %d",i<5 ? "Manual":"Auto",i%5+1);
            if(m->compatible) {
                time_t t=(time_t)m->timestamp;struct tm *date=localtime(&t);
                if(date)strftime(stamp,sizeof stamp,"%Y-%m-%d %H:%M",date);
                snprintf(detail,sizeof detail,"%s  Game %02u:%02u",stamp,m->game_time/100%24,m->game_time%100*60/100);
            } else snprintf(detail,sizeof detail,"%s",m->present ? "Incompatible / damaged":"Empty");
            rings_settings_label(h,x,y,scale,label);
            rings_settings_label(h,x,y+11*scale,scale,detail);
        }
        rings_settings_label(h,x,panel.y+panel.h-27*scale,scale,"Up/Down: Select - Enter/X/Z: Pick - Esc: Back");
        if(s->message[0])rings_settings_label(h,x,panel.y+panel.h-14*scale,scale,s->message);
    }
    SDL_RenderSetClipRect(h->renderer,NULL);
    SDL_SetRenderDrawBlendMode(h->renderer,SDL_BLENDMODE_NONE);SDL_SetRenderDrawColor(h->renderer,0,0,0,255);
}
static void rings_save_host_loaded(SDLHost *h,CPU *c) {
    sdl_pad_clear(&h->input);
    if(h->settings.ready) {c->ram[0x132]=0;c->ram[0x133]=(uint8_t)h->settings.help;}
#ifdef GENESIS_RINGS_WIDE
    rings_mouse_reset(&h->mouse);
#endif
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
    rings_camera_reset(&h->camera);
#endif
    rings_save_input_clear(c);h->stopped=0;h->last_frame=UINT64_MAX;h->next_service=c->master_cycles;
    h->fast_forward=0;h->audio_running=0;
    if(h->audio_device)SDL_ClearQueuedAudio(h->audio_device);
    SDL_SetWindowTitle(h->window,h->paused ? "RROP - paused":"RROP");
    sdl_host_rebase(h,c);h->saves->loaded=0;
}
static int rings_save_event(SDLHost *h,CPU *c,const SDL_Event *event) {
    RingsSaves *s=h->saves;if(!s)return 0;
    if(event->type!=SDL_KEYDOWN && event->type!=SDL_KEYUP)return s->menu && event->type!=SDL_WINDOWEVENT;
    int down=event->type==SDL_KEYDOWN;SDL_Keycode key=event->key.keysym.sym;
    if(s->menu) {
        if(down && !event->key.repeat) {
            int rows=s->menu==1 ? 5:10;
            if(key==SDLK_UP)s->selected=(s->selected+rows-1)%rows;
            if(key==SDLK_DOWN)s->selected=(s->selected+1)%rows;
            if(key==SDLK_ESCAPE) {s->menu=0;s->message[0]=0;sdl_pad_clear(&h->input);rings_save_input_clear(c);sdl_host_rebase(h,c);}
            if(key==SDLK_RETURN || key==SDLK_x || key==SDLK_z) {
                int ok=s->menu==1 ? rings_save_write(s,c,s->selected):rings_save_load(s,c,s->selected);
                if(ok) {sdl_pad_clear(&h->input);s->menu=0;if(s->loaded)rings_save_host_loaded(h,c);else sdl_host_rebase(h,c);s->notice_until=rings_save_now(h)+4000;}
            }
        }
        return 1;
    }
    if(down && !event->key.repeat && (key==SDLK_F5 || key==SDLK_F9)) {
        sdl_pad_clear(&h->input);rings_save_menu(s,c,key==SDLK_F5 ? 1:2);h->fast_forward=0;sdl_host_rebase(h,c);
        if(!s->menu)s->notice_until=rings_save_now(h)+4000;
        return 1;
    }
    return 0;
}
#endif
#endif
