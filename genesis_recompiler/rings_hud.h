/* Relocate only the verified gameplay footer. Pixels, numbers and parchment
   still come from the live VDP; menu/dialogue layouts retain their coordinates. */
#ifndef GENESIS_RINGS_HUD_H
#define GENESIS_RINGS_HUD_H
#ifdef GENESIS_RINGS_WIDE
typedef struct {int sx,sy,w,h,x,y;} RingsHudRegion;
static const RingsHudRegion rings_hud_regions[4]={
    {48,160,56,16,20,96}, {80,176,56,16,20,120},
    {112,192,40,16,20,144}, {246,152,64,64,332,152}
};
enum {RINGS_HUD_PAPER_X=4,RINGS_HUD_PAPER_Y=84,
      RINGS_HUD_PAPER_WIDTH=80,RINGS_HUD_PAPER_HEIGHT=132,
      RINGS_HUD_COMPASS_X=18,RINGS_HUD_COMPASS_Y=164,
      RINGS_HUD_COMPASS_WIDTH=64,RINGS_HUD_COMPASS_HEIGHT=45};
static int rings_hud_contains(int x,int y,int left,int top,int width,int height) {
    return x>=left && x<left+width && y>=top && y<top+height;
}
static int rings_hud_zone(int x,int y) {
    for(unsigned i=0;i<4;++i) {
        const RingsHudRegion *r=&rings_hud_regions[i];
        if(rings_hud_contains(x,y,r->sx,r->sy,r->w,r->h))return (int)i;
    }
    return -1;
}
static int rings_hud_text_position(const VDP *v,int x,int y,int *to_x,int *to_y) {
    int zone=rings_hud_zone(x,y);
    if(!rings_view_wide(v) || !v->wide_hud_active || zone<0)return 0;
    const RingsHudRegion *r=&rings_hud_regions[zone];
    *to_x=r->x+x-r->sx;*to_y=r->y+y-r->sy;return 1;
}
static int rings_hud_label(const VDP *v,unsigned base,unsigned x,unsigned y,const char *text) {
    for(unsigned i=0;text[i];++i) {
        unsigned at=0x1000+((y/8)*64+x/8+i)*2;
        if(vdp_word(v,at)!=(uint16_t)(base+(unsigned char)text[i]-32))return 0;
    }
    return 1;
}
static int rings_hud_layout(const VDP *v) {
    if(v->frame_width!=320 || v->frame_height<216)return 0;
    unsigned entry=vdp_word(v,0x1000+(20*64+6)*2);
    if(!(entry&0x8000) || (entry&0x7ff)<('G'-32))return 0;
    unsigned font_base=entry-('G'-32);
    if(!rings_hud_label(v,font_base,48,160,"Gold") ||
       !rings_hud_label(v,font_base,80,176,"Time") ||
       !rings_hud_label(v,font_base,112,192,"F/W"))return 0;
    /* The four live portrait-frame sprites are the original parchment asset.
       Reject another layout rather than borrowing a face or a controller tile. */
    unsigned base=(v->registers[5]&0x7e)<<9,link=0,found=0;
    uint8_t visited[128]={0};
    for(unsigned n=0;n<80;++n) {
        if(link>=80 || visited[link])break;
        visited[link]=1;
        unsigned at=base+link*8,size=vdp_word(v,at+2),pattern=vdp_word(v,at+4);
        int x=(int)(vdp_word(v,at+6)&511)-128,y=(int)(vdp_word(v,at)&1023)-128;
        if((size&0x0f00)==0x0f00 && (pattern&0xe000)==0x2000) {
            if(x==246 && y==152 && (pattern&0x1fff)==0x06ca)found|=1;
            if(x==278 && y==152 && (pattern&0x1fff)==0x06fa)found|=2;
            if(x==246 && y==184 && (pattern&0x1fff)==0x16ca)found|=4;
            if(x==278 && y==184 && (pattern&0x1fff)==0x16fa)found|=8;
        }
        link=size&127;if(!link)break;
    }
    return found==15;
}
/* Keep the original curled ends and side borders at their native scale.
   Widen the paper's interior once: repeating its shaded left edge produced
   a vertical stripe. The source contains no face: it is sprite-only art. */
static unsigned rings_hud_paper(const uint8_t *sprites,int x,int y) {
    int dx=x-RINGS_HUD_PAPER_X,dy=y-RINGS_HUD_PAPER_Y;
    if(dx<0 || dx>=RINGS_HUD_PAPER_WIDTH || dy<0 || dy>=RINGS_HUD_PAPER_HEIGHT)return 0;
    int sx=dx<12 ? dx:dx>=RINGS_HUD_PAPER_WIDTH-8 ? 64-(RINGS_HUD_PAPER_WIDTH-dx):
           12+(dx-12)*44/(RINGS_HUD_PAPER_WIDTH-20);
    int sy=dy<16 ? dy:dy>=RINGS_HUD_PAPER_HEIGHT-16 ? 64-(RINGS_HUD_PAPER_HEIGHT-dy):
           (dx<12 || dx>=RINGS_HUD_PAPER_WIDTH-8) ? 24:16+(dy-16)%32;
    return sprites[(152+sy)*320+246+sx]&63;
}
#endif
#endif
