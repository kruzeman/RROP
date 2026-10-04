/* Shared drawable/window geometry for the adaptive outdoor view and input. */
#ifndef GENESIS_RINGS_WINDOW_H
#define GENESIS_RINGS_WINDOW_H
#ifdef GENESIS_RINGS_WIDE
typedef struct {
    int width,height,adaptive,hud;
    double scale,x,y,world_scale,world_x,world_y;
} RingsWindowLayout;
static RingsWindowLayout rings_window_layout(const VDP *v,int width,int height,unsigned percent,double dx,double dy) {
    RingsWindowLayout p={0};p.width=width;p.height=height;
    unsigned vw=rings_view_width(v),vh=v->frame_height;
    if(width<=0 || height<=0 || !vw || !vh)return p;
    p.scale=(double)width/vw;
    if((double)height/vh<p.scale)p.scale=(double)height/vh;
    p.x=(width-vw*p.scale)*0.5;p.y=(height-vh*p.scale)*0.5;
    p.world_scale=p.scale;p.world_x=p.x;p.world_y=p.y;
    p.adaptive=rings_view_wide(v) && v->zoom_world_visible;
    p.hud=v->wide_hud_active;
    if(!p.adaptive)return p;
    /* At extreme aspect ratios / 50% zoom the frozen scene has finite edges.
       Fit that scene uniformly, independently of the HUD, rather than exposing
       its texture boundary or stretching pixels along one axis. */
    double zoom=percent/100.0;
    double tx=(int)v->zoom_focus_x-RINGS_ZOOM_LEFT+16-vw*0.5+dx;
    double ty=(int)v->zoom_focus_y-RINGS_ZOOM_TOP-vh*0.5+dy;
    double left=v->zoom_focus_x*zoom-tx,right=(RINGS_ZOOM_WIDTH-v->zoom_focus_x)*zoom+tx;
    double top=v->zoom_focus_y*zoom-ty,bottom=(RINGS_ZOOM_HEIGHT-v->zoom_focus_y)*zoom+ty;
    double horizontal=left<right ? left:right,vertical=top<bottom ? top:bottom;
    if(horizontal>0 && width/(2*horizontal)>p.world_scale)p.world_scale=width/(2*horizontal);
    if(vertical>0 && height/(2*vertical)>p.world_scale)p.world_scale=height/(2*vertical);
    p.world_x=(width-vw*p.world_scale)*0.5;p.world_y=(height-vh*p.world_scale)*0.5;
    return p;
}
/* A dialogue or menu remains one continuous canvas. Only the controller
   occupies its own top-right band; the ordinary HUD uses two lower corners. */
typedef struct {int x,y,w,h;} RingsWindowBand;
static RingsWindowBand rings_window_ui_band(const RingsWindowLayout *p,unsigned i) {
    static const RingsWindowBand hud[3]={{0,0,400,84},{0,84,200,140},{200,84,200,140}};
    static const RingsWindowBand menu[3]={{0,0,200,84},{200,0,200,84},{0,84,400,140}};
    return p->hud ? hud[i]:menu[i];
}
static void rings_window_ui_origin(const RingsWindowLayout *p,int x,int y,double *ox,double *oy) {
    *ox=p->x;*oy=p->y;
    if(!p->adaptive)return;
    if(!p->hud && !(y<84 && x>=200)) {
        *ox=p->x;*oy=p->height-224*p->scale;return;
    }
    *ox=y<84 || x>=200 ? p->width-RINGS_WIDE_WIDTH*p->scale:0;
    *oy=y<84 ? 0:p->height-224*p->scale;
}
static int rings_window_ui_hit(const RingsWindowLayout *p,const VDP *v,double x,double y) {
    if(!p->adaptive)return 0;
    for(unsigned i=0;i<3;++i) {
        RingsWindowBand band=rings_window_ui_band(p,i);
        double ox,oy;rings_window_ui_origin(p,band.x,band.y,&ox,&oy);
        double ux=(x-ox)/p->scale,uy=(y-oy)/p->scale;
        if(ux>=band.x && ux<band.x+band.w && uy>=band.y && uy<band.y+band.h &&
           !v->zoom_mask[(unsigned)uy*400+(unsigned)ux])return 1;
    }
    return 0;
}
#endif
#endif
