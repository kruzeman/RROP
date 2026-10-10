/* Numeric player HP is presentation-only; native bars and combat stay intact. */
#ifndef GENESIS_RINGS_HP_H
#define GENESIS_RINGS_HP_H
#ifdef GENESIS_RINGS_WIDE
static void rings_hp_draw(CPU *c,uint8_t *frame,unsigned width,unsigned offset,int protect) {
    VDP *v=&c->vdp;
    if(!v->zoom_enabled || v->frame_width!=320 || v->frame_height<176 ||
       (!rings_scene_word(c,0xac) && (rings_scene_context(c)!=0xffb0bc ||
       rings_scene_word(c,0xe7e)!=4)))return;
    unsigned owner=rings_scene_word(c,0x2b2),actor=56;
    unsigned displayed=rings_scene_word(c,0xe80);
    for(unsigned i=0;i<57;++i) {
        unsigned n=i==0 ? displayed:i-1;
        if(n>=56)continue;
        unsigned at=0x2b4+n*52;
        if((rings_scene_word(c,at)&15)==4 && c->ram[at+39]==owner &&
           rings_scene_word(c,at+32)>0 && rings_scene_word(c,at+32)<32768) {actor=n;break;}
    }
    if(actor>=56)return;
    unsigned at=0x2b4+actor*52;
    int menu=rings_scene_word(c,0xac)!=0 && rings_scene_context(c)!=0xffb0bc;
    /* Native bar builder 0278B2/02793A reads HP 28/32 and mana 30/34. */
    for(unsigned stat=0;stat<2;++stat) {
        unsigned max=rings_scene_word(c,at+32+stat*2);
        int current=(int16_t)rings_scene_word(c,at+28+stat*2);
        if(current<0)current=0;
        if((unsigned)current>max)current=(int)max;
        char text[24];snprintf(text,sizeof text,"%d/%u",current,max);
        unsigned length=(unsigned)strlen(text);
        unsigned left=menu ? (length*8<=80 ? 92-length*8:12):80;
        unsigned top=menu ? 106+stat*10:170+stat*10;
        unsigned bank=rings_scene_word(c,0x8640);
        /* Match the native bars' red and blue palette colors. */
        unsigned rgb=stat ? 0xe00:0x00e;
        for(unsigned n=0;text[n];++n) {
            unsigned entry=(bank+0x8000+(unsigned char)text[n]-32)&0xffff;
            for(unsigned y=0;y<8;++y)for(unsigned x=0;x<8;++x) {
                if(!(vdp_tile_pixel(v,entry,x,y)&15))continue;
                unsigned screen=(top+y)*width+offset+left+n*8+x,pixel=screen*3;
                frame[pixel]=vdp_channel((rgb>>1)&7,1);
                frame[pixel+1]=vdp_channel((rgb>>5)&7,1);
                frame[pixel+2]=vdp_channel((rgb>>9)&7,1);
                if(protect) {v->zoom_mask[screen]=0;v->zoom_restore[screen]=0;}
            }
        }
    }
}
static void rings_hp_frame(CPU *c,uint8_t *frame) {
    rings_hp_draw(c,frame,320,0,0);
}
#endif
#endif
