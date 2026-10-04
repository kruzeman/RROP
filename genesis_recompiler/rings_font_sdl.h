/* External fonts are rasterized at drawable resolution, after console scaling. */
#ifndef GENESIS_RINGS_FONT_SDL_H
#define GENESIS_RINGS_FONT_SDL_H
#include <SDL_ttf.h>
typedef struct {
    SDL_Texture *texture;
    SDL_Rect ink;
    int min_x,min_y,max_y,advance,ready;
} RingsGlyph;
typedef struct {
    const char *path;
    TTF_Font *font;
    RingsGlyph glyphs[128];
    int initialized, pixels, requested_pixels, cell_height, descent;
    double cap_ratio;
} RingsFont;
static void rings_font_clear(RingsFont *f) {
    for(unsigned i=0;i<128;++i) {
        SDL_DestroyTexture(f->glyphs[i].texture);
        memset(&f->glyphs[i],0,sizeof f->glyphs[i]);
    }
    if(f->font)TTF_CloseFont(f->font);
    f->font=NULL; f->pixels=0;f->requested_pixels=0;f->cell_height=0;
}
static void rings_font_close(RingsFont *f) {
    rings_font_clear(f);
    if(f->initialized)TTF_Quit();
    f->initialized=0; f->path=NULL;
}
static int rings_font_open(RingsFont *f,const char *path) {
    if(TTF_Init())return 0;
    f->initialized=1; f->path=path;
    f->font=TTF_OpenFont(path,32); f->pixels=32;
    if(!f->font)return 0;
    int min_x,max_x,min_y,max_y,advance;
    if(TTF_GlyphMetrics(f->font,'M',&min_x,&max_x,&min_y,&max_y,&advance) || max_y<=0)
        return SDL_SetError("external font has no usable Latin cap height"),0;
    f->cap_ratio=32.0/(max_y-TTF_FontDescent(f->font));
    return 1;
}
static int rings_font_extent(RingsFont *f,int *height) {
    int ascent=0,descent=TTF_FontDescent(f->font);
    for(unsigned ch=33;ch<127;++ch)if(TTF_GlyphIsProvided(f->font,(Uint16)ch)) {
        int min_x,max_x,min_y,max_y,advance;
        if(TTF_GlyphMetrics(f->font,(Uint16)ch,&min_x,&max_x,&min_y,&max_y,&advance))return 0;
        if(max_y>ascent)ascent=max_y;
        if(min_y<descent)descent=min_y;
    }
    f->descent=descent;*height=ascent-descent;return 1;
}
static int rings_font_size(RingsFont *f,double scale) {
    int pixels=(int)(8.0*scale*f->cap_ratio+0.5);
    if(pixels<1)pixels=1;
    if(pixels>4096)pixels=4096;
    int available=(int)(8.0*scale);
    if(available<1)available=1;
    if(pixels==f->requested_pixels && available==f->cell_height)return f->font!=NULL;
    int requested=pixels;
    rings_font_clear(f);
    for(;;) {
        f->font=TTF_OpenFont(f->path,pixels);f->pixels=pixels;
        if(!f->font)return 0;
        int height;
        if(!rings_font_extent(f,&height))return 0;
        if(height<=available || pixels==1)break;
        TTF_CloseFont(f->font);f->font=NULL;--pixels;
    }
    f->requested_pixels=requested;f->cell_height=available;
    return 1;
}
static int rings_font_glyph(RingsFont *f,SDL_Renderer *renderer,unsigned ch) {
    RingsGlyph *g=&f->glyphs[ch];
    if(g->ready)return 1;
    if(!TTF_GlyphIsProvided(f->font,(Uint16)ch))return SDL_SetError("external font is missing character '%c'",ch),0;
    int max_x;
    if(TTF_GlyphMetrics(f->font,(Uint16)ch,&g->min_x,&max_x,&g->min_y,&g->max_y,&g->advance))return 0;
    if(ch==' ') { g->ready=1;return 1; }
    SDL_Color white={255,255,255,255};
    SDL_Surface *surface=TTF_RenderGlyph_Blended(f->font,(Uint16)ch,white);
    if(!surface)return 0;
    /* Crop the transparent line box, retaining the glyph's baseline metrics. */
    int left=surface->w,top=surface->h,right=-1,bottom=-1;
    if(SDL_LockSurface(surface)) { SDL_FreeSurface(surface); return 0; }
    for(int y=0;y<surface->h;++y)for(int x=0;x<surface->w;++x) {
        Uint32 pixel; memcpy(&pixel,(Uint8 *)surface->pixels+y*surface->pitch+x*4,4);
        Uint8 r,gg,b,a; SDL_GetRGBA(pixel,surface->format,&r,&gg,&b,&a);
        if(a) { if(x<left)left=x; if(x>right)right=x; if(y<top)top=y; if(y>bottom)bottom=y; }
    }
    SDL_UnlockSurface(surface);
    if(right<left || bottom<top) { SDL_FreeSurface(surface); return SDL_SetError("external font returned an empty glyph"),0; }
    g->ink=(SDL_Rect){left,top,right-left+1,bottom-top+1};
    g->texture=SDL_CreateTextureFromSurface(renderer,surface);
    SDL_FreeSurface(surface);
    g->ready=g->texture!=NULL;return g->ready;
}
/* Only contiguous, visible cells from the same captured invocation can move
   together. A different row, layer, string, or bitmap fallback splits the run. */
static unsigned rings_font_run_end(const VDP *v,unsigned first) {
    unsigned end=first+1;
    while(end<v->font_count) {
        const RingsTextVisible *previous=&v->font_cells[end-1],*next=&v->font_cells[end];
        if(!previous->run || next->run!=previous->run || next->layer!=previous->layer ||
           next->y!=previous->y || next->x!=previous->x+8)break;
#ifdef GENESIS_RINGS_WIDE
        if(rings_view_wide(v) && v->wide_hud_active && rings_hud_zone(next->x,next->y)!=rings_hud_zone(previous->x,previous->y))break;
#endif
        ++end;
    }
    return end;
}
typedef struct {
    double x[40], origin, fit, width;
} RingsLineLayout;
static int rings_font_layout(RingsFont *f,SDL_Renderer *renderer,const VDP *v,
                             unsigned first,unsigned end,double available,RingsLineLayout *layout) {
    if(end<=first || end-first>40 || available<=0)return SDL_SetError("invalid captured text span"),0;
    double pen=0,left=0,right=0;
    unsigned previous=0;
    for(unsigned i=first;i<end;++i) {
        unsigned ch=v->font_cells[i].ch;
        if(!rings_font_glyph(f,renderer,ch))return 0;
        if(previous && TTF_GetFontKerning(f->font))
            pen+=TTF_GetFontKerningSizeGlyphs(f->font,(Uint16)previous,(Uint16)ch);
        RingsGlyph *g=&f->glyphs[ch];
        layout->x[i-first]=pen;
        if(ch!=' ') {
            double start=pen+g->min_x,stop=start+g->ink.w;
            if(start<left)left=start;
            if(stop>right)right=stop;
        }
        pen+=g->advance;
        if(pen>right)right=pen;
        previous=ch;
    }
    layout->width=right-left;
    layout->fit=layout->width>available ? available/layout->width:1.0;
    layout->origin=-left*layout->fit;
    return 1;
}
static int rings_font_draw_view(RingsFont *f,SDL_Renderer *renderer,const VDP *v,const SDL_Rect *viewport,double scale
#ifdef GENESIS_RINGS_WIDE
                                ,const RingsWindowLayout *canvas
#endif
) {
    if(!v->font_count)return 1;
    if(!rings_font_size(f,scale))return 0;
    for(unsigned i=0;i<v->font_count;) {
        const RingsTextVisible *cell=&v->font_cells[i];
        unsigned end=rings_font_run_end(v,i);
        int draw_x=cell->x,draw_y=cell->y,origin_x=viewport->x,origin_y=viewport->y;
#ifdef GENESIS_RINGS_WIDE
        int relocated_x,relocated_y;
        if(rings_hud_text_position(v,draw_x,draw_y,&relocated_x,&relocated_y)) {
            /* Use the full-canvas origin and positive destination coordinates.
               Rounding a negative relative clip edge would cut a glyph column. */
            origin_x-=(int)(40*scale+0.5);
            draw_x=relocated_x;draw_y=relocated_y;
        }
        if(canvas && canvas->adaptive) {
            if(draw_x==cell->x && draw_y==cell->y)draw_x+=40;
            double ox,oy;rings_window_ui_origin(canvas,draw_x,draw_y,&ox,&oy);
            origin_x=(int)(ox+0.5);origin_y=(int)(oy+0.5);
        }
#endif
        double left=draw_x*scale,right=left+(v->font_cells[end-1].x+8-cell->x)*scale;
        int clip_left=origin_x+(int)(left+0.5),clip_right=origin_x+(int)(right+0.5);
        int clip_top=origin_y+(int)(draw_y*scale+0.5);
        SDL_Rect clip={
            clip_left,clip_top,clip_right-clip_left,
            origin_y+(int)((draw_y+8)*scale+0.5)-clip_top};
        RingsLineLayout layout;
        if(!rings_font_layout(f,renderer,v,i,end,right-left,&layout) || SDL_RenderSetClipRect(renderer,&clip))return 0;
        for(unsigned j=i;j<end;++j) {
            const RingsTextVisible *letter=&v->font_cells[j];
            if(letter->ch==' ')continue;
            RingsGlyph *g=&f->glyphs[letter->ch];
            SDL_FRect to={
                (float)(origin_x+left+layout.origin+(layout.x[j-i]+g->min_x)*layout.fit),
                (float)(origin_y+draw_y*scale+8*scale+f->descent-g->max_y),
                (float)(g->ink.w*layout.fit),(float)g->ink.h};
            if(SDL_SetTextureColorMod(g->texture,letter->rgb[0],letter->rgb[1],letter->rgb[2]) ||
               SDL_RenderCopyF(renderer,g->texture,&g->ink,&to))return 0;
        }
        i=end;
    }
    return SDL_RenderSetClipRect(renderer,NULL)==0;
}
static int rings_font_draw(RingsFont *f,SDL_Renderer *renderer,const VDP *v,const SDL_Rect *viewport,double scale) {
    return rings_font_draw_view(f,renderer,v,viewport,scale
#ifdef GENESIS_RINGS_WIDE
                                ,NULL
#endif
    );
}

#endif
