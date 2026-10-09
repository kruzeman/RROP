/* Rings host settings, reached through the original main and SYSTEM menus. */
#ifndef GENESIS_RINGS_SETTINGS_SDL_H
#define GENESIS_RINGS_SETTINGS_SDL_H
#if defined(GENESIS_RINGS_SAVES) && defined(GENESIS_SDL2)
static void rings_settings_write(SDLHost *h) {
    RingsSettings *s=&h->settings;
    if(!s->path[0]) {snprintf(s->message,sizeof s->message,"Settings directory unavailable");return;}
    char data[512],temp[1280];
    int n=snprintf(data,sizeof data,"GenesisRecomp Settings 1\nenhanced=%d\nwide=%d\nfullscreen=%d\nsmooth=%d\nzoom=%d\nmouse=%d\nhelp=%d\ngamepad=%d\npad_layout=%d\npad_custom=%d\npad_a=%u\npad_b=%u\npad_c=%u\npad_start=%u\n",
                   s->enhanced,s->wide,s->fullscreen,s->smooth,s->zoom,s->mouse,s->help,h->input.enabled,h->input.layout,
                   h->input.custom,sdl_pad_binding(&h->input,0),sdl_pad_binding(&h->input,1),
                   sdl_pad_binding(&h->input,2),sdl_pad_binding(&h->input,3));
#ifdef _WIN32
    snprintf(temp,sizeof temp,"%s.tmp.%ld",s->path,(long)_getpid());
    wchar_t target[1280],temporary[1280];
    int ok=rings_save_wide(s->path,target,1280) && rings_save_wide(temp,temporary,1280);
    HANDLE fd=ok ? CreateFileW(temporary,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL):INVALID_HANDLE_VALUE;
    ok=fd!=INVALID_HANDLE_VALUE;
    if(ok) {ok=rings_save_write_all(fd,(const uint8_t *)data,(size_t)n) && FlushFileBuffers(fd);if(!CloseHandle(fd))ok=0;}
    if(ok)ok=MoveFileExW(temporary,target,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)!=0;
    if(!ok && fd!=INVALID_HANDLE_VALUE)DeleteFileW(temporary);
#else
    snprintf(temp,sizeof temp,"%s.tmp.%ld",s->path,(long)getpid());
    int fd=open(temp,O_WRONLY|O_CREAT|O_TRUNC,0600),ok=fd>=0;
    if(ok) {ok=rings_save_write_all(fd,(const uint8_t *)data,(size_t)n) && !fsync(fd);if(close(fd))ok=0;}
    if(ok)ok=!rename(temp,s->path);
    if(!ok)unlink(temp);
#endif
    if(!ok)snprintf(s->message,sizeof s->message,"Cannot save settings - previous file preserved");
}
static void rings_settings_apply(SDLHost *h,CPU *c) {
    RingsSettings *s=&h->settings;
    int full=s->enhanced && s->fullscreen;
    if(SDL_SetWindowFullscreen(h->window,full ? SDL_WINDOW_FULLSCREEN_DESKTOP:0)) {
        s->fullscreen=!!(SDL_GetWindowFlags(h->window)&SDL_WINDOW_FULLSCREEN_DESKTOP);
        snprintf(s->message,sizeof s->message,"Cannot change fullscreen mode");
    }
#ifdef GENESIS_RINGS_WIDE
    c->vdp.wide_enabled=(uint8_t)(s->enhanced && s->wide);
    /* Enhanced response uses the completed scene even at 100% with mouse,
       zoom and smooth scrolling disabled. Their UI toggles remain independent. */
    c->vdp.zoom_enabled=(uint8_t)s->enhanced;
    h->zoom_percent=s->enhanced && s->zoom ? s->saved_zoom:100;
    rings_pad_reset(&h->pad_intent);rings_mouse_reset(&h->mouse);h->mouse.enabled=s->enhanced && s->mouse;
    rings_scene_discard(c);
    if(c->wide) {
        memset(&c->wide->motion,0,sizeof c->wide->motion);
        c->wide->motion.enabled=h->responsive_movement && s->enhanced;
        c->wide->motion.intent=&h->pad_intent;
    }
#endif
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
    rings_camera_reset(&h->camera);h->camera.enabled=s->enhanced && s->smooth;
#endif
#ifdef GENESIS_RINGS_MENU_FONT
    c->vdp.font_enabled=(uint8_t)(s->enhanced && h->font.path);
#endif
    sdl_pad_clear(&h->input);rings_save_input_clear(c);h->fast_forward=0;h->last_frame=UINT64_MAX;
    if(c->vdp.rendered_frames)vdp_render(c);
    sdl_host_rebase(h,c);
}
static void rings_settings_init(SDLHost *h,CPU *c,int wide,int zoom,int mouse,int smooth) {
    RingsSettings *s=&h->settings;s->ready=1;s->saved_zoom=100;
    c->rings_settings_enabled=1;s->help=0;
    s->enhanced=wide || zoom || mouse || smooth;
#ifdef GENESIS_RINGS_MENU_FONT
    s->enhanced|=h->font.path!=NULL;
#endif
    s->wide=s->enhanced ? wide:1;s->zoom=s->enhanced ? zoom:1;
    s->mouse=s->enhanced ? mouse:1;s->smooth=s->enhanced ? smooth:1;
    if(h->saves && h->saves->enabled) {
        size_t directory_size=strlen(h->saves->directory);
        if(directory_size<=sizeof s->path-sizeof "/settings.cfg") {
            memcpy(s->path,h->saves->directory,directory_size);
            memcpy(s->path+directory_size,"/settings.cfg",sizeof "/settings.cfg");
        } else {s->path[0]=0;snprintf(s->message,sizeof s->message,"Settings directory path is too long");}
        FILE *f=s->path[0] ? rings_save_read_file(s->path):NULL;
        if(f) {
            char line[128];uint8_t binding[4]={0};unsigned seen=0;int custom=0;
            if(fgets(line,sizeof line,f) && !strcmp(line,"GenesisRecomp Settings 1\n")) {
                while(fgets(line,sizeof line,f)) {
                    char key[32],tail;int value;
                    if(sscanf(line,"%31[^=]=%d %c",key,&value,&tail)!=2)continue;
                    const char *keys[4]={"pad_a","pad_b","pad_c","pad_start"};
                    for(unsigned i=0;i<4;++i)if(!strcmp(key,keys[i])) {
                        seen|=1u<<i;binding[i]=(uint8_t)(value>=0 && value<SDL_CONTROLLER_BUTTON_MAX ? value:255);
                    }
                    if(value!=0 && value!=1)continue;
                    if(!strcmp(key,"pad_custom"))custom=value;
                    if(!strcmp(key,"enhanced"))s->enhanced=value;
                    if(!strcmp(key,"wide"))s->wide=value;
                    if(!strcmp(key,"fullscreen"))s->fullscreen=value;
                    if(!strcmp(key,"smooth"))s->smooth=value;
                    if(!strcmp(key,"zoom"))s->zoom=value;
                    if(!strcmp(key,"mouse"))s->mouse=value;
                    if(!strcmp(key,"help"))s->help=value;
                    if(!strcmp(key,"gamepad"))h->input.enabled=value;
                    if(!strcmp(key,"pad_layout"))h->input.layout=value;
                }
                h->input.custom=custom && seen==15 && sdl_pad_bindings_valid(binding);
                if(h->input.custom)memcpy(h->input.binding,binding,sizeof binding);
            }
            fclose(f);
        }
    }
#ifndef GENESIS_RINGS_WIDE
    s->wide=s->zoom=s->mouse=0;
#endif
#ifndef GENESIS_RINGS_SMOOTH_CAMERA
    s->smooth=0;
#endif
    rings_settings_apply(h,c);
}
static void rings_settings_open(SDLHost *h,CPU *c) {
    RingsSettings *s=&h->settings;s->menu=1;s->selected=0;s->controls=0;s->remap=0;s->message[0]=0;
    sdl_pad_clear(&h->input);rings_save_input_clear(c);h->fast_forward=0;
#ifdef GENESIS_RINGS_WIDE
    rings_pad_reset(&h->pad_intent);rings_mouse_reset(&h->mouse);
#endif
    h->next_service=c->master_cycles;h->last_frame=UINT64_MAX;sdl_host_rebase(h,c);
}
static void rings_settings_close(SDLHost *h,CPU *c) {
    h->settings.menu=0;h->settings.controls=0;h->settings.remap=0;
    sdl_pad_clear(&h->input);rings_save_input_clear(c);sdl_host_rebase(h,c);h->last_frame=UINT64_MAX;
}
static void rings_settings_observe(SDLHost *h,CPU *c) {
    RingsSettings *s=&h->settings;
    if(!s->ready || s->menu || c->fault)return;
    /* Native Help (command $12) toggles the controller hint at $FF0132.
       Keep this presentation preference independent of a loaded game slot. */
    if(c->pc==0x20388) {
        s->help=!!(c->ram[0x132] || c->ram[0x133]);rings_settings_write(h);
    }
    if(c->pc==0xd28e) {c->ram[0x132]=0;c->ram[0x133]=(uint8_t)s->help;}
    if(c->pc==0x158c2) {
        /* Sixth label uses the game's own loaded font and original plane. */
        unsigned bank=((unsigned)c->ram[0x8640]<<8)|c->ram[0x8641];
#ifdef GENESIS_RINGS_MENU_FONT
        if(!++c->vdp.font_run)c->vdp.font_run=1;
#endif
        for(unsigned i=0;i<8;++i) {
            unsigned ch=(unsigned char)"Settings"[i],at=0x2000+18*128+(17+i)*2;
            uint16_t entry=(uint16_t)(bank+0x8000+ch-32);
            c->vdp.vram[at]=(uint8_t)(entry>>8);c->vdp.vram[at+1]=(uint8_t)entry;
#ifdef GENESIS_RINGS_MENU_FONT
            RingsTextMark *m=&c->vdp.font_marks[at/2];m->entry=entry;m->ch=(uint8_t)ch;
            m->run=c->vdp.font_run;m->pattern=rings_text_pattern(&c->vdp,entry&0x7ff);
#endif
        }
    }
    if(c->pc==0x15a3c) {
        unsigned at=(c->a[6]-2)&65535;
        if((((unsigned)c->ram[at]<<8)|c->ram[(at+1)&65535])==5) {
            c->pc=0x1591e;rings_settings_open(h,c);
        }
    }
    if(c->pc==0x20172 && c->ram[0xbb6c]==0xfd) {
        /* Resume the existing command cleanup after returning from settings. */
        c->ram[0xbb6c]=0;c->pc=0x20758;rings_settings_open(h,c);
    }
}
static void rings_settings_remap_start(SDLHost *h) {
    RingsSettings *s=&h->settings;
    if(!h->input.controller || !SDL_GameControllerGetAttached(h->input.controller)) {
        snprintf(s->message,sizeof s->message,"Connect a gamepad first");return;
    }
    s->remap=1;s->remap_held=0;s->message[0]=0;
    for(unsigned i=0;i<SDL_CONTROLLER_BUTTON_MAX && i<32;++i)
        if(SDL_GameControllerGetButton(h->input.controller,(SDL_GameControllerButton)i))s->remap_held|=UINT32_C(1)<<i;
    sdl_pad_clear(&h->input);
}
/* Consume raw buttons before host-menu key translation: B must be assignable
   here rather than interpreted as Escape. Commit all four bindings together. */
static int rings_settings_remap_event(SDLHost *h,CPU *c,const SDL_Event *e) {
    RingsSettings *s=&h->settings;if(!s->menu || !s->remap)return 0;
    if(((e->type==SDL_CONTROLLERDEVICEREMOVED || e->type==SDL_CONTROLLERDEVICEREMAPPED) &&
        e->cdevice.which==h->input.instance) ||
       (e->type==SDL_WINDOWEVENT && e->window.event==SDL_WINDOWEVENT_FOCUS_LOST)) {
        s->remap=0;snprintf(s->message,sizeof s->message,"Button assignment cancelled");return 0;
    }
    if(e->type==SDL_KEYDOWN && !e->key.repeat &&
       (e->key.keysym.sym==SDLK_ESCAPE || e->key.keysym.sym==SDLK_F10)) {
        s->remap=0;s->message[0]=0;
        return e->key.keysym.sym==SDLK_ESCAPE;
    }
    if(e->type==SDL_CONTROLLERBUTTONDOWN || e->type==SDL_CONTROLLERBUTTONUP) {
        if(e->cbutton.which!=h->input.instance || !h->input.focused)return 1;
        unsigned b=e->cbutton.button;if(b>=SDL_CONTROLLER_BUTTON_MAX || b>=32)return 1;
        uint32_t bit=UINT32_C(1)<<b;
        if(e->type==SDL_CONTROLLERBUTTONUP) {s->remap_held&=~bit;return 1;}
        if(b==SDL_CONTROLLER_BUTTON_BACK) {s->remap=0;s->message[0]=0;sdl_pad_clear(&h->input);return 1;}
        if(s->remap_held) {s->remap_held|=bit;return 1;}
        s->remap_held|=bit;
        if(!sdl_pad_bindable(b)) {
            snprintf(s->message,sizeof s->message,"This button is reserved for movement or menus");return 1;
        }
        unsigned step=(unsigned)s->remap-1;
        for(unsigned i=0;i<step;++i)if(s->remap_binding[i]==b) {
            snprintf(s->message,sizeof s->message,"Already assigned - choose another button");return 1;
        }
        s->remap_binding[step]=(uint8_t)b;s->message[0]=0;
        if(++s->remap==5) {
            memcpy(h->input.binding,s->remap_binding,sizeof h->input.binding);h->input.custom=1;
            s->remap=0;sdl_pad_clear(&h->input);rings_save_input_clear(c);
            rings_settings_write(h);
            if(!s->message[0])snprintf(s->message,sizeof s->message,"Gamepad buttons saved");
        }
        return 1;
    }
    if(e->type==SDL_CONTROLLERAXISMOTION || e->type==SDL_KEYDOWN || e->type==SDL_KEYUP)return 1;
    return 0;
}
static int rings_settings_event(SDLHost *h,CPU *c,const SDL_Event *e) {
    RingsSettings *s=&h->settings;if(!s->ready)return 0;
    if(e->type==SDL_KEYDOWN && !e->key.repeat && e->key.keysym.sym==SDLK_F10 &&
       (!h->saves || !h->saves->menu)) {
        if(s->menu)rings_settings_close(h,c);else rings_settings_open(h,c);return 1;
    }
    if(!s->menu)return 0;
    if(e->type==SDL_WINDOWEVENT)return 0;
    if(e->type==SDL_KEYDOWN && !e->key.repeat) {
        SDL_Keycode key=e->key.keysym.sym;int rows=s->enhanced ? 9:4;
        if(key==SDLK_ESCAPE) {
            if(s->controls)s->controls=0;else rings_settings_close(h,c);
        } else if(s->controls) {
            if(key==SDLK_UP)s->control_selected=(s->control_selected+4)%5;
            if(key==SDLK_DOWN)s->control_selected=(s->control_selected+1)%5;
            if(key==SDLK_RETURN || key==SDLK_x || key==SDLK_z || key==SDLK_LEFT || key==SDLK_RIGHT) {
                sdl_pad_clear(&h->input);
                if(s->control_selected==0)h->input.enabled=!h->input.enabled;
                else if(s->control_selected==1) {h->input.layout=!h->input.layout;h->input.custom=0;}
                else if(s->control_selected==2) {rings_settings_remap_start(h);return 1;}
                else if(s->control_selected==3) {h->input.layout=0;h->input.custom=0;s->message[0]=0;}
                else s->controls=0;
                sdl_pad_clear(&h->input);rings_settings_write(h);
            }
        } else {
            if(key==SDLK_UP)s->selected=(s->selected+rows-1)%rows;
            if(key==SDLK_DOWN)s->selected=(s->selected+1)%rows;
            if(key==SDLK_RETURN || key==SDLK_x || key==SDLK_z || key==SDLK_LEFT || key==SDLK_RIGHT) {
                int back=s->enhanced ? 7:2;
                if(s->selected==back+1) {
                    SDL_Event quit;SDL_zero(quit);quit.type=SDL_QUIT;SDL_PushEvent(&quit);
                } else if(s->selected==back)rings_settings_close(h,c);
                else if(s->selected==(s->enhanced ? 6:1)) {s->controls=1;s->control_selected=0;}
                else {
                    int *toggle=NULL;
                    switch(s->selected) {
                        case 0:toggle=&s->enhanced;break;
                        case 1:toggle=&s->wide;break;
                        case 2:toggle=&s->fullscreen;break;
                        case 3:toggle=&s->smooth;break;
                        case 4:toggle=&s->zoom;break;
                        case 5:toggle=&s->mouse;break;
                    }
#ifndef GENESIS_RINGS_WIDE
                    if(s->selected==1 || s->selected==4 || s->selected==5)toggle=NULL;
#endif
#ifndef GENESIS_RINGS_SMOOTH_CAMERA
                    if(s->selected==3)toggle=NULL;
#endif
                    if(toggle) {s->message[0]=0;*toggle=!*toggle;rings_settings_apply(h,c);rings_settings_write(h);}
                    else snprintf(s->message,sizeof s->message,"Rebuild with this feature enabled");
                }
            }
        }
    }
    return 1;
}
/* Cache only parchment sprites; no letters, selection bar or portrait pixels. */
static void rings_settings_paper(SDLHost *h,const VDP *v) {
    RingsSettings *s=&h->settings;if(s->paper_width)return;
    uint8_t paper[96*64*4]={0};unsigned found=0,width=0;
    unsigned base=(v->registers[5]&0x7e)<<9,link=0;uint8_t visited[80]={0};
    for(unsigned n=0;n<80 && link<80 && !visited[link];++n) {
        visited[link]=1;unsigned at=base+link*8,size=vdp_word(v,at+2),entry=vdp_word(v,at+4);
        int left=(int)(vdp_word(v,at+6)&511)-128,top=(int)(vdp_word(v,at)&1023)-128;
        int x=-1,y=-1;
        if((size&0x0f00)==0x0f00) {
            if((left==116 || left==148 || left==180) && (top==93 || top==125)) {
                x=left-116;y=top-93;width=96;found|=1u<<((unsigned)(y/32)*3+(unsigned)x/32);
            } else if(!width && (left==246 || left==278) && (top==152 || top==184) &&
                      (entry&0x7ff)==(left==246 ? 0x6ca:0x6fa)) {width=64;}
            if(width==64 && (left==246 || left==278) && (top==152 || top==184) &&
               (entry&0x7ff)==(left==246 ? 0x6ca:0x6fa)) {
                x=left-246;y=top-152;found|=1u<<((unsigned)(y/32)*2+(unsigned)x/32);
            }
        }
        if(x>=0)for(unsigned dy=0;dy<32;++dy)for(unsigned dx=0;dx<32;++dx) {
            unsigned sx=entry&0x800 ? 31-dx:dx,sy=entry&0x1000 ? 31-dy:dy;
            unsigned tile=(entry&0x7ff)+(sx/8)*4+sy/8,ink=vdp_pattern(v,tile,sx&7,sy&7);
            uint8_t *out=paper+(((unsigned)y+dy)*96+(unsigned)x+dx)*4;
            unsigned color=v->cram[ink|((entry>>9)&0x30)];
            out[0]=vdp_channel((color>>1)&7,1);out[1]=vdp_channel((color>>5)&7,1);
            out[2]=vdp_channel((color>>9)&7,1);out[3]=ink ? 255:0;
        }
        link=size&127;if(!link)break;
    }
    if((width==96 && found==63) || (width==64 && found==15)) {
        memcpy(s->paper,paper,sizeof paper);s->paper_width=width;
    }
}
static void rings_settings_label(SDLHost *h,int x,int y,int scale,const char *label) {
#ifdef GENESIS_RINGS_MENU_FONT
    if(h->font.path) {
        SDL_Color color={20,12,10,255};SDL_Surface *surface=TTF_RenderUTF8_Blended(h->font.font,label,color);
        if(surface) {
            SDL_Texture *texture=SDL_CreateTextureFromSurface(h->renderer,surface);
            SDL_Rect to={x,y,(int)((double)surface->w/surface->h*10*scale),10*scale};
            if(texture) {SDL_RenderCopy(h->renderer,texture,NULL,&to);SDL_DestroyTexture(texture);}
            SDL_FreeSurface(surface);return;
        }
    }
#endif
    SDL_SetRenderDrawColor(h->renderer,20,12,10,255);rings_save_text(h->renderer,x,y+scale,scale,label,48);
}
/* Shared parchment and ink for Settings, save/load slots and save notices. */
static void rings_settings_panel(SDLHost *h,SDL_Rect panel,int scale) {
    RingsSettings *s=&h->settings;
    if(s->paper_width) {
        /* Tile only the unshaded interior at the original texel size. Keep
           the curled ends and side borders instead of stretching their grain. */
        unsigned native_height=(unsigned)(panel.h/scale),native_width=(unsigned)(panel.w/scale);
        if(!s->paper_texture || s->panel_height!=native_height || s->panel_width!=native_width) {
            SDL_DestroyTexture(s->paper_texture);s->paper_texture=NULL;
            uint8_t *pixels=malloc(native_width*native_height*4);
            if(pixels) {
                for(unsigned py=0;py<native_height;++py)for(unsigned px=0;px<native_width;++px) {
                    unsigned sx=px<12 ? px:px>=native_width-8 ? s->paper_width-(native_width-px):20+(px-12)%(s->paper_width-32);
                    unsigned sy=py<16 ? py:py>=native_height-16 ? 64-(native_height-py):16+(py-16)%32;
                    memcpy(pixels+(py*native_width+px)*4,s->paper+(sy*96+sx)*4,4);
                }
                s->paper_texture=SDL_CreateTexture(h->renderer,SDL_PIXELFORMAT_RGBA32,SDL_TEXTUREACCESS_STATIC,(int)native_width,(int)native_height);
                if(s->paper_texture) {
                    SDL_UpdateTexture(s->paper_texture,NULL,pixels,(int)native_width*4);
                    SDL_SetTextureBlendMode(s->paper_texture,SDL_BLENDMODE_BLEND);s->panel_height=native_height;s->panel_width=native_width;
                }
                free(pixels);
            }
        }
        if(s->paper_texture)SDL_RenderCopy(h->renderer,s->paper_texture,NULL,&panel);
    } else {
        SDL_SetRenderDrawColor(h->renderer,69,37,16,255);SDL_RenderFillRect(h->renderer,&panel);
        SDL_Rect paper={panel.x+6*scale,panel.y+6*scale,panel.w-12*scale,panel.h-12*scale};
        SDL_SetRenderDrawColor(h->renderer,204,105,103,255);SDL_RenderFillRect(h->renderer,&paper);
    }

}
static void rings_settings_overlay(SDLHost *h,const VDP *v) {
    RingsSettings *s=&h->settings;if(!s->ready)return;
    rings_settings_paper(h,v);
    if(!s->menu)return;
    int width,height;SDL_GetRendererOutputSize(h->renderer,&width,&height);
    if(width<=0 || height<=0)return;
    SDL_RenderSetLogicalSize(h->renderer,0,0);SDL_RenderSetScale(h->renderer,1,1);
    SDL_RenderSetViewport(h->renderer,NULL);SDL_RenderSetClipRect(h->renderer,NULL);
    SDL_SetRenderDrawBlendMode(h->renderer,SDL_BLENDMODE_BLEND);
    SDL_SetRenderDrawColor(h->renderer,0,0,0,150);SDL_RenderFillRect(h->renderer,NULL);
    int rows=s->remap ? 6:s->controls ? 11:s->enhanced ? 9:4;
    int native_height=rows*16+58;
    int scale=width/300;if(height/native_height<scale)scale=height/native_height;if(scale<1)scale=1;
    int ph=(rows*16+58)*scale,pw=280*scale;
    SDL_Rect panel={(width-pw)/2,(height-ph)/2,pw,ph};
    rings_settings_panel(h,panel,scale);
    int x=panel.x+20*scale,y=panel.y+12*scale;
    rings_settings_label(h,x,y,scale,s->remap ? "Assign gamepad buttons":s->controls ? "Control settings":"Settings");y+=22*scale;
    if(s->remap) {
        const char *names[4]={"A","B","C","START"};
        for(unsigned i=0;i<4;++i,y+=16*scale) {
            char label[64];
            if((int)i==s->remap-1) {
                SDL_Rect row={panel.x+16*scale,y-2*scale,panel.w-32*scale,14*scale};
                SDL_SetRenderDrawColor(h->renderer,255,248,232,255);SDL_RenderFillRect(h->renderer,&row);
                snprintf(label,sizeof label,"Press button for Genesis %s",names[i]);
            } else if((int)i<s->remap-1)snprintf(label,sizeof label,"Genesis %s: %s",names[i],sdl_pad_label(s->remap_binding[i]));
            else snprintf(label,sizeof label,"Genesis %s: ...",names[i]);
            rings_settings_label(h,x,y,scale,label);
        }
        rings_settings_label(h,x,y+8*scale,scale,s->remap_held ? "Release held buttons to continue":"Choose a button on your gamepad");
    } else if(s->controls) {
        for(int i=0;i<5;++i,y+=16*scale) {
            if(i==s->control_selected) {
                SDL_Rect row={panel.x+16*scale,y-2*scale,panel.w-32*scale,14*scale};
                SDL_SetRenderDrawColor(h->renderer,255,248,232,255);SDL_RenderFillRect(h->renderer,&row);
            }
            char label[64];
            if(i==0)snprintf(label,sizeof label,"Gamepad: %s",h->input.enabled ? "On":"Off");
            else if(i==1)snprintf(label,sizeof label,"Layout: %s",h->input.custom ? "Custom":h->input.layout ? "A / B / X":"X / A / B");
            else if(i==2)snprintf(label,sizeof label,"Assign buttons: A / B / C / START");
            else if(i==3)snprintf(label,sizeof label,"Reset buttons");
            else snprintf(label,sizeof label,"Back");
            rings_settings_label(h,x,y,scale,label);
        }
        const char *device=h->input.controller ? SDL_GameControllerName(h->input.controller):NULL;
        char label[64];snprintf(label,sizeof label,"Pad: %.25s",device ? device:"Not connected");
        rings_settings_label(h,x,y+8*scale,scale,label);
        rings_settings_label(h,x,y+24*scale,scale,"Move: D-pad / Left stick");
        snprintf(label,sizeof label,"A/B/C: %s / %s / %s",sdl_pad_label(sdl_pad_binding(&h->input,0)),
                 sdl_pad_label(sdl_pad_binding(&h->input,1)),sdl_pad_label(sdl_pad_binding(&h->input,2)));
        rings_settings_label(h,x,y+40*scale,scale,label);
        snprintf(label,sizeof label,"START: %s",sdl_pad_label(sdl_pad_binding(&h->input,3)));
        rings_settings_label(h,x,y+56*scale,scale,label);
        rings_settings_label(h,x,y+72*scale,scale,"Settings: Back / Share / -");
        rings_settings_label(h,x,y+88*scale,scale,"Save / Load: LB / RB");
    } else for(int i=0;i<rows;++i,y+=16*scale) {
        if(i==s->selected) {
            SDL_Rect row={panel.x+16*scale,y-2*scale,panel.w-32*scale,14*scale};
            SDL_SetRenderDrawColor(h->renderer,255,248,232,255);SDL_RenderFillRect(h->renderer,&row);
        }
        char label[64];const char *names[5]={"Widescreen","Fullscreen","Smooth map","Zoom","Mouse controls"};
        int values[5]={s->wide,s->fullscreen,s->smooth,s->zoom,s->mouse};
        if(i==0)snprintf(label,sizeof label,"Mode: %s",s->enhanced ? "Enhanced":"Classic");
        else if(i==(s->enhanced ? 8:3))snprintf(label,sizeof label,"Exit");
        else if(i==(s->enhanced ? 7:2))snprintf(label,sizeof label,"Back");
        else if(i==(s->enhanced ? 6:1))snprintf(label,sizeof label,"Control settings");
        else snprintf(label,sizeof label,"%s: %s",names[i-1],values[i-1] ? "On":"Off");
        rings_settings_label(h,x,y,scale,label);
    }
    y=panel.y+ph-21*scale;
    rings_settings_label(h,x,y,scale,s->remap ? "Esc / Back: Cancel":"Arrows / Enter - Esc: Back");
    if(s->message[0])rings_settings_label(h,panel.x, panel.y+ph+3*scale,scale,s->message);
    SDL_SetRenderDrawBlendMode(h->renderer,SDL_BLENDMODE_NONE);SDL_SetRenderDrawColor(h->renderer,0,0,0,255);
}
#endif
#endif
