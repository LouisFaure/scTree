import numpy as np
import pandas as pd
from anndata import AnnData

import igraph
import seaborn as sns
import matplotlib.pyplot as plt
from matplotlib.colors import to_hex
from matplotlib.gridspec import GridSpec
from scipy import stats
from adjustText import adjust_text
from matplotlib import patches
from scipy import sparse

import warnings
from . import palette_tools
from typing import Union, Optional
from scanpy.plotting._utils import savefig_or_show

from .. import logging as logg

def cluster(
    adata: AnnData,
    clu = None,
    features = None,
    combi=True,
    root_milestone = None,
    milestones = None,
    cell_size=20,
    quant_ord=.7,
    figsize: tuple = (20,12),
    basis: str = "umap",
    colormap: str = "magma",
    emb_back = None,
    show: Optional[bool] = None,
    save: Union[str, bool, None] = None):
    
    if 'edgecolor' not in kwargs:
        kwargs['edgecolor'] = 'none'
    
    fitted = pd.DataFrame(adata.layers["fitted"],index=adata.obs_names,columns=adata.var_names).T.copy(deep=True)
    g = adata.obs.groupby('seg')
    seg_order=g.apply(lambda x: np.mean(x.t)).sort_values().index.tolist()
    cell_order=np.concatenate(list(map(lambda x: adata.obs.t[adata.obs.seg==x].sort_values().index,seg_order)))
    fitted=fitted.loc[:,cell_order]
    fitted=fitted.apply(lambda x: (x-x.mean())/x.std(),axis=1)

    seg=adata.obs["seg"].copy(deep=True)
    
    
    color_key = "seg_colors"
    if color_key not in adata.uns or len(adata.uns[color_key]):
        palette_tools._set_default_colors_for_categorical_obs(adata,"seg")
    pal=dict(zip(adata.obs["seg"].cat.categories,adata.uns[color_key]))

    segs = seg.astype(str).map(pal)
    segs.name = "segs"


    # Get the color map by name:
    cm = plt.get_cmap('viridis')

    pseudotime = cm(adata.obs.t[cell_order]/adata.obs.t[cell_order].max())

    pseudotime = list(map(to_hex,pseudotime.tolist()))

    col_colors=pd.concat([segs,pd.Series(pseudotime,name="pseudotime",index=cell_order)],axis=1,sort=False)
    
    
    def get_in_clus_order(c):
        test=fitted.loc[clusters.index[clusters==c],:]
        start_cell=adata.obs_names[adata.obs.t==adata.obs.loc[test.idxmax(axis=1).values,"t"].sort_values().iloc[0]]
        early_feature=test.index[test.idxmax(axis=1).isin(start_cell)][0]

        ix = test.T.corr(method="pearson").sort_values(early_feature, ascending=False).index
        return ix
        

    if clu is not None:
        clusters = adata.var["fit_clusters"]
        fitted=fitted.loc[clusters.index[clusters==clu],:]
        fitted_sorted = fitted.loc[get_in_clus_order(clu), :]
    else:
        fitted=fitted.loc[features,:]
        varia=list(map(lambda x: adata.obs.t[cell_order][fitted.loc[x,:].values>np.quantile(fitted.loc[x,:].values,q=quant_ord)].var(),features))

        z = np.abs(stats.zscore(varia))
        torem = np.argwhere(z > 3)

        if len(torem)>0:
            torem=torem[0]
            logg.info("found "+str(len(torem))+" complex fitted features")
            logg.hint( "added\n" + "    'complex' column in (adata.var)")
            adata.var["complex"]=False
            adata.var.complex.iloc[torem]=True
            features=adata.var_names[~adata.var["complex"]]
        
        fitted = fitted.loc[features,:]
        list(map(lambda x: adata.obs.t[fitted.loc[x,:].values>np.quantile(fitted.loc[x,:].values,q=quant_ord)].mean(),features))
        ix = fitted.apply(lambda x: adata.obs.t[x>np.quantile(x,q=quant_ord)].mean(),axis=1).sort_values().index
        fitted_sorted = fitted.loc[ix, :]

    
    
    if root_milestone is not None:
        dct = dict(zip(adata.copy().obs.milestones.cat.categories.tolist(),
                   np.unique(adata.uns["tree"]["pp_seg"][["from","to"]].values.flatten().astype(int))))
        keys = np.array(list(dct.keys()))
        vals = np.array(list(dct.values()))

        leaves = list(map(lambda leave: dct[leave],milestones))
        root = dct[root_milestone]
        df = adata.obs.copy(deep=True)
        edges=adata.uns["tree"]["pp_seg"][["from","to"]].astype(str).apply(tuple,axis=1).values
        img = igraph.Graph()
        img.add_vertices(np.unique(adata.uns["tree"]["pp_seg"][["from","to"]].values.flatten().astype(str)))
        img.add_edges(edges)
        cells=np.unique(np.concatenate([getpath(img,root,adata.uns["tree"]["tips"],leaves[0],adata.uns["tree"],df).index,
                       getpath(img,root,adata.uns["tree"]["tips"],leaves[1],adata.uns["tree"],df).index]))

        col_colors=col_colors[col_colors.index.isin(cells)]
        fitted_sorted=fitted_sorted.loc[:,fitted_sorted.columns.isin(cells)]
        
    else:
        cells=None
    
    

    hm=sns.clustermap(fitted_sorted,figsize=figsize,dendrogram_ratio=0, colors_ratio=0.03,robust=True,cmap=colormap,
                row_cluster=False,col_cluster=False,col_colors=col_colors,cbar_pos=None,xticklabels=False)
    if combi:
        hm.gs.update(left=0.526)
        gs2 = GridSpec(1,1, left=0.05,right=0.50)
        ax2 = hm.fig.add_subplot(gs2[0])
        
        if emb_back is not None:
            ax2.scatter(emb_back[:,0],emb_back[:,1],s=cell_size,color="lightgrey",edgecolor="none")
        
        if cells is not None:
            ax2.scatter(adata.obsm["X_"+basis][~adata.obs_names.isin(cells),0],
                        adata.obsm["X_"+basis][~adata.obs_names.isin(cells),1],
                        c="lightgrey",s=cell_size,edgecolor="none")
            ax2.scatter(adata.obsm["X_"+basis][adata.obs_names.isin(cells),0],
                        adata.obsm["X_"+basis][adata.obs_names.isin(cells),1],
                        c="black",s=cell_size*2,edgecolor="none")
            ax2.scatter(adata.obsm["X_"+basis][adata.obs_names.isin(cells),0],
                        adata.obsm["X_"+basis][adata.obs_names.isin(cells),1],
                        s=cell_size,edgecolor="none",
                        c=fitted.mean(axis=0)[adata[adata.obs_names.isin(cells),:].obs_names],cmap=colormap)
        else:
            cells = adata.obs_names
            ax2.scatter(adata.obsm["X_"+basis][:,0],
                        adata.obsm["X_"+basis][:,1],
                        s=cell_size,edgecolor="none",
                        c=fitted.mean(axis=0)[adata[adata.obs_names.isin(cells),:].obs_names],cmap=colormap)
        ax2.grid(False)
        x0,x1 = ax2.get_xlim()
        y0,y1 = ax2.get_ylim()
        ax2.set_aspect(abs(x1-x0)/abs(y1-y0))
        ax2.tick_params(
            axis='both',          # changes apply to the x-axis
            which='both',      # both major and minor ticks are affected
            bottom=False,      # ticks along the bottom edge are off
            top=False,         # ticks along the top edge are off
            labelbottom=False,
            left=False,
            labelleft=False) # labels along the bottom edge are off
        ax2.set_xlabel(basis+"1",fontsize=18)
        ax2.set_ylabel(basis+"2",fontsize=18)
        for axis in ['top','bottom','left','right']:
            ax2.spines[axis].set_linewidth(2)
    
    savefig_or_show('cluster', show=show, save=save)

    
def linear_trends(
    adata: AnnData,
    features = None,
    highlight_features = None,
    n_features: int = 10,
    root_milestone = None,
    milestones = None,
    cell_size=20,
    quant_ord=.7,
    figsize: tuple = (8,8),
    frame: Union[float,None] = 2,
    basis: str = "umap",
    colormap: str = "RdBu_r",
    pseudo_colormap: str = "viridis",
    emb_back = None,
    show: Optional[bool] = None,
    save: Union[str, bool, None] = None):
    
    if features is None:
        features = adata.var_names
    
    fitted = pd.DataFrame(adata.layers["fitted"],index=adata.obs_names,columns=adata.var_names).T.copy(deep=True)
    g = adata.obs.groupby('seg')
    seg_order=g.apply(lambda x: np.mean(x.t)).sort_values().index.tolist()
    cell_order=np.concatenate(list(map(lambda x: adata.obs.t[adata.obs.seg==x].sort_values().index,seg_order)))
    fitted=fitted.loc[:,cell_order]
    fitted=fitted.apply(lambda x: (x-x.mean())/x.std(),axis=1)

    seg=adata.obs["seg"].copy(deep=True)
    
    
    color_key = "seg_colors"
    if color_key not in adata.uns or len(adata.uns[color_key]):
        palette_tools._set_default_colors_for_categorical_obs(adata,"seg")
    pal=dict(zip(adata.obs["seg"].cat.categories,adata.uns[color_key]))

    segs = seg.astype(str).map(pal)
    segs.name = "segs"


    fitted=fitted.loc[features,:]
    varia=list(map(lambda x: adata.obs.t[cell_order][fitted.loc[x,:].values>np.quantile(fitted.loc[x,:].values,q=quant_ord)].var(),features))

    z = np.abs(stats.zscore(varia))
    torem = np.argwhere(z > 3)

    if len(torem)>0:
        torem=torem[0]
        logg.info("found "+str(len(torem))+" complex fitted features")
        logg.hint( "added\n" + "    'complex' column in (adata.var)")
        adata.var["complex"]=False
        adata.var.complex.iloc[torem]=True
        features=adata.var_names[~adata.var["complex"]]

    fitted = fitted.loc[features,:]
    #list(map(lambda x: adata.obs.t[fitted.loc[x,:].values>np.quantile(fitted.loc[x,:].values,q=quant_ord)].mean(),features))
    ix = fitted.apply(lambda x: adata.obs.t[x>np.quantile(x,q=quant_ord)].mean(),axis=1).sort_values().index
    fitted_sorted = fitted.loc[ix, :]

    
    
    if root_milestone is not None:
        dct = dict(zip(adata.copy().obs.milestones.cat.categories.tolist(),
                   np.unique(adata.uns["tree"]["pp_seg"][["from","to"]].values.flatten().astype(int))))
        keys = np.array(list(dct.keys()))
        vals = np.array(list(dct.values()))

        leaves = list(map(lambda leave: dct[leave],milestones))
        root = dct[root_milestone]
        df = adata.obs.copy(deep=True)
        edges=adata.uns["tree"]["pp_seg"][["from","to"]].astype(str).apply(tuple,axis=1).values
        img = igraph.Graph()
        img.add_vertices(np.unique(adata.uns["tree"]["pp_seg"][["from","to"]].values.flatten().astype(str)))
        img.add_edges(edges)
        cells=np.unique(np.concatenate([getpath(img,root,adata.uns["tree"]["tips"],leaves[0],adata.uns["tree"],df).index,
                       getpath(img,root,adata.uns["tree"]["tips"],leaves[1],adata.uns["tree"],df).index]))

        fitted_sorted=fitted_sorted.loc[:,fitted_sorted.columns.isin(cells)]
        
    else:
        cells=None
    
    
    fig, (ax,ax2) = plt.subplots(ncols=1,nrows=2,figsize=figsize,gridspec_kw={'height_ratios':[1,figsize[1]*2]})
    fig.subplots_adjust(hspace=0.01)

    sns.heatmap(pd.DataFrame(adata.obs.t[fitted_sorted.columns].values).T,robust=True,cmap=pseudo_colormap,xticklabels=False,yticklabels=False,cbar=False,ax=ax,vmax=adata.obs.t.max())
        
    sns.heatmap(fitted_sorted,robust=True,cmap=colormap,xticklabels=False,yticklabels=False,ax=ax2,cbar=False)
    
    if frame is not None:
        ax.hlines(y=0,xmin=0,xmax=fitted_sorted.shape[1]-frame, color='k',linewidth=frame*2)
        ax.hlines(y=1,xmin=0,xmax=fitted_sorted.shape[1]-frame, color='k',linewidth=frame*2)
        ax.vlines(x=0, ymin=0, ymax=1, color='k',linewidth=frame*2)
        ax.vlines(x=len(fitted_sorted.columns), ymin=0, ymax=1, color='k',linewidth=frame)
        ax2.hlines(y=0,xmin=0,xmax=fitted_sorted.shape[1]-frame, color='k',linewidth=frame*2)
        ax2.hlines(y=fitted_sorted.shape[0],xmin=0,xmax=fitted_sorted.shape[1]-frame, color='k',linewidth=frame*2)
        ax2.vlines(x=0,ymin=0,ymax=fitted_sorted.shape[0], color='k',linewidth=frame*2)
        ax2.vlines(x=fitted_sorted.shape[1],ymin=0,ymax=fitted_sorted.shape[0], color='k',linewidth=frame)

    if highlight_features is None:
        highlight_features = adata.var.A[features].sort_values(ascending=False)[:n_features].index
    xs=np.repeat(fitted_sorted.shape[1],len(highlight_features))  
    ys=np.array(list(map(lambda g: np.argwhere(fitted_sorted.index==g)[0][0],highlight_features)))+0.5
    
    texts = []
    for x, y, s in zip(xs, ys, highlight_features):
        texts.append(ax2.text(x, y, s))

    patch = patches.Rectangle((0, 0), fitted_sorted.shape[1]+fitted_sorted.shape[1]/6, fitted_sorted.shape[0], alpha=0) # We add a rectangle to make sure the labels don't move to the right    
    ax.set_xlim((0,fitted_sorted.shape[1]+fitted_sorted.shape[1]/3))
    ax2.set_xlim((0,fitted_sorted.shape[1]+fitted_sorted.shape[1]/3))
    ax2.add_patch(patch)

    adjust_text(texts,add_objects=[patch],arrowprops=dict(arrowstyle='-', color='k'),va="center",ha="left",autoalign=False,
        force_text=(0.05, 0.25), force_points=(0.05, 0.25),only_move={"points":"x", "text":"y", "objects":"x"})
    
    savefig_or_show('linear_trends', show=show, save=save)    
    
    
def single_trend(
    adata: AnnData,
    feature: str,
    basis: str = "umap",
    ylab = "expression",
    layer = None,
    colormap: str = "RdBu_r",
    colorexp = None,
    figsize = (10,5.5),
    emb_back = None,
    size_cells = None,
    highlight = False,
    alpha_expr = 0.3,
    size_expr = 2,
    fitted_linewidth = 2,
    show: Optional[bool] = None,
    save: Union[str, bool, None] = None):
  
    fig, (ax1, ax2) = plt.subplots(1, 2,figsize=figsize,constrained_layout=True)
    fig.suptitle(feature)
    

    ncells = adata.shape[0]
    
    if size_cells is None:
        size_cells = 30000 / ncells

    if emb_back is not None:
        ncells = emb_back.shape[0]
        if size_cells is None:
            size_cells = 30000 / ncells
        ax1.scatter(emb_back[:,0],emb_back[:,1],s=size_cells,color="lightgrey",edgecolor="none")
        
    if layer is None:
        if sparse.issparse(adata.X):
            Xfeature = adata[:,feature].X.A.T.flatten()
        else:
            Xfeature = adata[:,feature].X.T.flatten()
    else:
        if sparse.issparse(adata.layers[layer]):
            Xfeature = adata[:,feature].layers[layer].A.T.flatten()
        else:
            Xfeature = adata[:,feature].layers[layer].T.flatten()

    df=pd.DataFrame({"t":adata.obs.t,"fitted":adata[:,feature].layers["fitted"].flatten(),"expression":Xfeature,"seg":adata.obs.seg}).sort_values("t")

    if highlight:
        ax1.scatter(adata.obsm["X_"+basis][:,0],adata.obsm["X_"+basis][:,1],c="k",s=size_cells*2,edgecolor="none")

    ax1.scatter(adata.obsm["X_"+basis][:,0],adata.obsm["X_"+basis][:,1],c=df.fitted[adata.obs_names],s=size_cells,cmap=colormap,edgecolor="none")
    ax1.grid(b=False)
    ax1.set_xticks([])
    ax1.set_yticks([])
    ax1.set_xlabel(basis+"1")
    ax1.set_ylabel(basis+"2")
    x0,x1 = ax1.get_xlim()
    y0,y1 = ax1.get_ylim()
    ax1.set_aspect(abs(x1-x0)/abs(y1-y0))
    for s in df.seg.unique():
        if colorexp is None:
            ax2.scatter(df.loc[df.seg==s,"t"],df.loc[df.seg==s,"expression"],alpha=alpha_expr,s=size_expr)
            ax2.plot(df.loc[df.seg==s,"t"],df.loc[df.seg==s,"fitted"],linewidth=fitted_linewidth)
        else:
            ax2.scatter(df.loc[df.seg==s,"t"],df.loc[df.seg==s,"expression"],c=colorexp,alpha=alpha_expr,s=size_expr)
            ax2.plot(df.loc[df.seg==s,"t"],df.loc[df.seg==s,"fitted"],c=colorexp,linewidth=fitted_linewidth)

    ax2.set_ylabel(ylab)
    ax2.set_xlabel("pseudotime")
    x0,x1 = ax2.get_xlim()
    y0,y1 = ax2.get_ylim()
    ax2.set_aspect(abs(x1-x0)/abs(y1-y0))
    plt.tight_layout()
    
    savefig_or_show('single_trend', show=show, save=save)    
    
    
            
def getpath(g,root,tips,tip,tree,df):
    warnings.filterwarnings("ignore")
    try:
        path=np.array(g.vs[:]["name"])[np.array(g.get_shortest_paths(str(root),str(tip)))][0]
        segs = list()
        for i in range(len(path)-1):
            segs= segs + [np.argwhere((tree["pp_seg"][["from","to"]].astype(str).apply(lambda x: 
                                                                                    all(x.values == path[[i,i+1]]),axis=1)).to_numpy())[0][0]]
        segs=tree["pp_seg"].index[segs]
        pth=df.loc[df.seg.astype(int).isin(segs),:].copy(deep=True)
        pth["branch"]=str(root)+"_"+str(tip)
        warnings.filterwarnings("default")
        return(pth)
    except IndexError:
        pass
    