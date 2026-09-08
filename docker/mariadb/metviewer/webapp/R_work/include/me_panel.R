# Shared caption and ME panel for lead-time and diurnal profiles.
# Keep XML plot_cmd short to avoid command-field length limits.
draw_me_panel <- function(unit, date_field) {
    dd=as.Date(dfPlot[[date_field]]);
    dd=dd[!is.na(dd)];
    cap=paste0("WRF vs IMGW | ",min(dd)," -- ",max(dd)," | FULL domain");
    mtext(cap,side=3,line=0.3,adj=0,cex=0.8,col="#333333",las=1);
    f=par("fig");
    p=par("plt");
    u=par("usr");
    xL=f[1]+p[1]*diff(f[1:2]);
    xR=f[1]+p[2]*diff(f[1:2]);
    yB=f[3]+p[3]*diff(f[3:4]);
    yT=f[3]+p[4]*diff(f[3:4]);
    h2=(yT-yB)/4;
    y1=yB-0.01;
    y0=y1-h2;
    me=listSeries2[[1]];
    r=range(c(me,0),na.rm=TRUE);
    z=.08*diff(r);
    if(!is.finite(z)||z==0)z=.1;
    yl=max(abs(r+c(-z,z)));
    yl=ceiling(yl*2)/2;
    yt=c(-yl,0,yl);
    par(fig=c(xL,xR,y0,y1),mar=c(0,0,0,0),new=TRUE);
    plot(listX,me,type="n",xlim=u[1:2],xaxs="i",ylim=c(-yl,yl),axes=FALSE,xlab="",ylab="");
    xp=par("xpd");
    par(xpd=isTRUE(0));
    abline(h=yt,col="#cccccc",lty=3,lwd=.8);
    abline(h=0,col="#555555",lty=2,lwd=1);
    par(xpd=xp);
    lines(listX,me,type="b",pch=20,col="#8000ffFF");
    axis(1,at=listX[seq(1,length(listX),2)],labels=FALSE,tcl=.35);
    axis(2,at=yt,las=1,padj=.5,hadj=.5,cex.axis=1,tcl=.35);
    box();
    mtext(paste0("ME [",unit,"]"),xpd=NA,side=2,line=1,padj=-2,adj=.5,cex=1,font=1,las=0);
}
