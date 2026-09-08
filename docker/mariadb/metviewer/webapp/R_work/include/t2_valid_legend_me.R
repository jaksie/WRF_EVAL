# T2 valid-time plot: white legend padding, caption and lower ME panel.
# Loaded from the METviewer R_work directory before closing the graphics device.
# Legend placement matches the T2 fbar_obar_me_by_valid.xml profile.
local({
    legend_args=list(x="bottom", legend=listLegendDisp, col=listColorsDisp, lty=listLtyDisp, lwd=listLwdLeg, pch=listPchDisp, merge=FALSE, cex=0.8, bty="o", adj=0, xpd=TRUE, ncol=3, inset=c(0, -.55), x.intersp=1, y.intersp=.8);
    legend_bounds=do.call(legend,c(legend_args,list(plot=FALSE)))$rect;
    legend_pad_x=xinch(0.08);
    legend_pad_y=yinch(0.08);
    rect(legend_bounds$left-legend_pad_x,legend_bounds$top-legend_bounds$h-legend_pad_y,legend_bounds$left+legend_bounds$w+legend_pad_x,legend_bounds$top+legend_pad_y,col="white",border=NA,xpd=NA);
    do.call(legend,c(legend_args,list(bg="white")));
    dd=as.Date(dfPlot$fcst_valid_beg);
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
    axis(1,at=listX[seq(1,length(listX),2)],labels=FALSE);
    axis(2,at=yt,las=1);
    box();
    mtext("ME [K]",side=2,line=2.8,cex=.9,las=0);
})
