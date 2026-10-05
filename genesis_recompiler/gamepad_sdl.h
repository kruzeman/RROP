/* Host input sources stay separate from serialized console state. */
#ifndef GENESIS_GAMEPAD_SDL_H
#define GENESIS_GAMEPAD_SDL_H
typedef struct {
    SDL_GameController *controller;
    SDL_JoystickID instance;
    uint8_t keyboard,blocked;
    int focused,enabled,layout,stick_x,stick_y;
} SDLPadInput;
static int sdl_pad_axis(int value,int previous) {
    if(value<=-10000)return -1;
    if(value>=10000)return 1;
    if(previous<0 && value<-8000)return -1;
    if(previous>0 && value>8000)return 1;
    return 0;
}
static uint8_t sdl_pad_physical(SDLPadInput *p) {
    if(!p->controller || !SDL_GameControllerGetAttached(p->controller))return 0;
    uint8_t buttons=0;
    const SDL_GameControllerButton face[2][3]={
        {SDL_CONTROLLER_BUTTON_X,SDL_CONTROLLER_BUTTON_A,SDL_CONTROLLER_BUTTON_B},
        {SDL_CONTROLLER_BUTTON_A,SDL_CONTROLLER_BUTTON_B,SDL_CONTROLLER_BUTTON_X}
    };
    for(unsigned i=0;i<3;++i)
        if(SDL_GameControllerGetButton(p->controller,face[p->layout!=0][i]))buttons|=(uint8_t)(PAD_A<<i);
    if(SDL_GameControllerGetButton(p->controller,SDL_CONTROLLER_BUTTON_START))buttons|=PAD_START;
    p->stick_x=sdl_pad_axis(SDL_GameControllerGetAxis(p->controller,SDL_CONTROLLER_AXIS_LEFTX),p->stick_x);
    p->stick_y=sdl_pad_axis(SDL_GameControllerGetAxis(p->controller,SDL_CONTROLLER_AXIS_LEFTY),p->stick_y);
    if(p->stick_x<0 || SDL_GameControllerGetButton(p->controller,SDL_CONTROLLER_BUTTON_DPAD_LEFT))buttons|=PAD_LEFT;
    if(p->stick_x>0 || SDL_GameControllerGetButton(p->controller,SDL_CONTROLLER_BUTTON_DPAD_RIGHT))buttons|=PAD_RIGHT;
    if(p->stick_y<0 || SDL_GameControllerGetButton(p->controller,SDL_CONTROLLER_BUTTON_DPAD_UP))buttons|=PAD_UP;
    if(p->stick_y>0 || SDL_GameControllerGetButton(p->controller,SDL_CONTROLLER_BUTTON_DPAD_DOWN))buttons|=PAD_DOWN;
    return buttons;
}
static void sdl_pad_clear(SDLPadInput *p) {
    p->keyboard=0;p->blocked=sdl_pad_physical(p);
}
static void sdl_pad_close(SDLPadInput *p) {
    if(p->controller)SDL_GameControllerClose(p->controller);
    p->controller=NULL;p->instance=-1;p->stick_x=p->stick_y=0;p->blocked=0;
}
static void sdl_pad_connect(SDLPadInput *p) {
    if(p->controller)return;
    for(int i=0;i<SDL_NumJoysticks();++i) {
        if(!SDL_IsGameController(i))continue;
        SDL_GameController *controller=SDL_GameControllerOpen(i);
        if(!controller)continue;
        p->controller=controller;
        p->instance=SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(controller));
        p->blocked=sdl_pad_physical(p);
        const char *name=SDL_GameControllerName(controller);
        fprintf(stderr,"gamepad: %s connected\n",name ? name:"Controller");break;
    }
}
static uint8_t sdl_pad_buttons(SDLPadInput *p,int suspended) {
    uint8_t physical=sdl_pad_physical(p);
    if(suspended || !p->focused) {
        p->keyboard=0;p->blocked=physical;return 0;
    }
    p->blocked&=physical;
    if(!p->enabled) {p->blocked=physical;physical=0;}
    uint8_t buttons=p->keyboard|(physical&(uint8_t)~p->blocked);
    if((buttons&(PAD_UP|PAD_DOWN))==(PAD_UP|PAD_DOWN))buttons&=(uint8_t)~(PAD_UP|PAD_DOWN);
    if((buttons&(PAD_LEFT|PAD_RIGHT))==(PAD_LEFT|PAD_RIGHT))buttons&=(uint8_t)~(PAD_LEFT|PAD_RIGHT);
    return buttons;
}
/* Translate only host-menu gestures. Native game input is polled separately. */
static int sdl_pad_event(SDLPadInput *p,SDL_Event *event,int menu) {
    if(event->type==SDL_CONTROLLERDEVICEADDED) {sdl_pad_connect(p);return 1;}
    if(event->type==SDL_CONTROLLERDEVICEREMOVED) {
        if(event->cdevice.which==p->instance) {sdl_pad_close(p);sdl_pad_connect(p);}
        return 1;
    }
    if(event->type==SDL_CONTROLLERDEVICEREMAPPED) {sdl_pad_clear(p);return 1;}
    int button=event->type==SDL_CONTROLLERBUTTONDOWN || event->type==SDL_CONTROLLERBUTTONUP;
    int axis=event->type==SDL_CONTROLLERAXISMOTION;
    if(!button && !axis)return 0;
    SDL_JoystickID which=button ? event->cbutton.which:event->caxis.which;
    if(which!=p->instance || !p->enabled || !p->focused)return 1;
    SDL_Keycode key=0;int down=button && event->type==SDL_CONTROLLERBUTTONDOWN;
    if(button) {
        unsigned b=event->cbutton.button;
        if(menu) {
            if(b==SDL_CONTROLLER_BUTTON_DPAD_UP)key=SDLK_UP;
            if(b==SDL_CONTROLLER_BUTTON_DPAD_DOWN)key=SDLK_DOWN;
            if(b==SDL_CONTROLLER_BUTTON_DPAD_LEFT)key=SDLK_LEFT;
            if(b==SDL_CONTROLLER_BUTTON_DPAD_RIGHT)key=SDLK_RIGHT;
            if(b==SDL_CONTROLLER_BUTTON_A || b==SDL_CONTROLLER_BUTTON_X || b==SDL_CONTROLLER_BUTTON_START)key=SDLK_RETURN;
            if(b==SDL_CONTROLLER_BUTTON_B)key=SDLK_ESCAPE;
        }
        if(b==SDL_CONTROLLER_BUTTON_BACK)key=menu ? SDLK_ESCAPE:SDLK_F10;
        if(!menu && b==SDL_CONTROLLER_BUTTON_LEFTSHOULDER)key=SDLK_F5;
        if(!menu && b==SDL_CONTROLLER_BUTTON_RIGHTSHOULDER)key=SDLK_F9;
    } else if(menu) {
        int horizontal=event->caxis.axis==SDL_CONTROLLER_AXIS_LEFTX;
        if(!horizontal && event->caxis.axis!=SDL_CONTROLLER_AXIS_LEFTY)return 1;
        int *previous=horizontal ? &p->stick_x:&p->stick_y;
        int next=sdl_pad_axis(event->caxis.value,*previous);
        if(next && next!=*previous) {
            key=horizontal ? (next<0 ? SDLK_LEFT:SDLK_RIGHT):(next<0 ? SDLK_UP:SDLK_DOWN);down=1;
        }
        *previous=next;
    }
    if(!key)return 1;
    SDL_zero(*event);event->type=down ? SDL_KEYDOWN:SDL_KEYUP;
    event->key.state=down ? SDL_PRESSED:SDL_RELEASED;event->key.keysym.sym=key;
    return 0;
}
#endif
