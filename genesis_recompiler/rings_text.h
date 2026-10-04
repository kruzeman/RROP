/* Build visible text from captured name-table cells and current VDP layers.
   Only complete aligned cells whose overlay order is verified are substituted. */
#ifndef GENESIS_RINGS_TEXT_H
#define GENESIS_RINGS_TEXT_H
static unsigned rings_text_source(const VDP *v,unsigned layer,unsigned x,unsigned y,
                                  unsigned *sx,unsigned *sy) {
    if(layer==1 && vdp_window_at(v,x,y)) {
        int h40=v->frame_width==320;
        unsigned base=(v->registers[3]&(h40 ? 0x3c:0x3e))<<10;
        *sx=x;*sy=y;
        return (base+((y/8)*(h40 ? 64:32)+x/8)*2)&65535;
    }
    return vdp_plane_address(v,layer==2,x,y,sx,sy);
}
static unsigned rings_text_ink(const VDP *v,unsigned tile) {
    unsigned ink=0;
    for(unsigned y=0;y<8;++y)for(unsigned x=0;x<8;++x) {
        unsigned nibble=vdp_pattern(v,tile,x,y);
        if(nibble) { if(ink && ink!=nibble)return 0;ink=nibble; }
    }
    return ink;
}
static void rings_text_prepare(VDP *v,unsigned width,unsigned height,const uint8_t *sprites) {
    memset(v->font_mask,0,sizeof v->font_mask);
    if(!(v->registers[1]&0x40) || (v->registers[12]&8))return;
    uint32_t hashes[2048]={0};
    uint8_t ready[2048]={0},inks[2048]={0};
    for(unsigned y=0;y+8<=height;y+=8)for(unsigned x=0;x+8<=width;x+=8) {
        for(unsigned layer=1;layer<=2;++layer) {
            unsigned sx,sy,at=rings_text_source(v,layer,x,y,&sx,&sy);
            if((at&1) || (sx&7) || (sy&7))continue;
            const RingsTextMark *mark=&v->font_marks[at/2];
            if(!mark->ch || !v->font_supported[mark->ch])continue;
            unsigned entry=vdp_word(v,at),tile=entry&0x7ff;
            if(entry!=mark->entry || (entry&0x1800))continue;
            if(!ready[tile]) {
                ready[tile]=1;hashes[tile]=rings_text_pattern(v,tile);
                inks[tile]=(uint8_t)rings_text_ink(v,tile);
            }
            if(hashes[tile]!=mark->pattern || (mark->ch==' ' ? inks[tile]!=0:inks[tile]==0))continue;
            int visible=1;
            for(unsigned yy=0;yy<8 && visible;++yy)for(unsigned xx=0;xx<8;++xx) {
                unsigned px=x+xx,py=y+yy,mx,my;
                if(rings_text_source(v,layer,px,py,&mx,&my)!=at ||
                   (mx&7)!=xx || (my&7)!=yy) { visible=0;break; }
                unsigned s=sprites[py*width+px];
                unsigned other=layer==1 ? vdp_plane_pixel(v,1,px,py):
                    (vdp_window_at(v,px,py) ? vdp_window_pixel(v,px,py,width==320):vdp_plane_pixel(v,0,px,py));
                /* Reject a cell if another foreground layer can cover it.
                   Low-priority selection bars remain beneath high-priority A. */
                if(entry&0x8000) {
                    if((s&128) || (layer==2 && (other&128) && (other&15)))visible=0;
                } else if((s&15) || ((other&15) && (layer==2 || (other&128))))visible=0;
                if(!visible)break;
            }
            if(!visible)continue;
            RingsTextVisible *cell=&v->font_cells[v->font_count++];
            cell->x=(uint16_t)x;cell->y=(uint16_t)y;cell->ch=mark->ch;
            cell->run=mark->run;cell->layer=(uint8_t)layer;
            if(mark->ch!=' ')++v->font_visible;
            unsigned rgb=v->cram[((entry>>9)&0x30)|inks[tile]];
            cell->rgb[0]=(uint8_t)(((rgb>>1)&7)*255/7);
            cell->rgb[1]=(uint8_t)(((rgb>>5)&7)*255/7);
            cell->rgb[2]=(uint8_t)(((rgb>>9)&7)*255/7);
            for(unsigned yy=0;yy<8;++yy)for(unsigned xx=0;xx<8;++xx)
                v->font_mask[(y+yy)*width+x+xx]|=(uint8_t)layer;
            /* At most one text layer is visible in a complete screen cell. */
            break;
        }
    }
}
#endif
