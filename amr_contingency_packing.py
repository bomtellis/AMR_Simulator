"""Deterministic, non-overlapping lift floor arrangements for people and loads."""
from functools import lru_cache

OPERATOR_DEFAULTS=dict(operator_length_m=.6,operator_width_m=.6,operator_height_m=1.8)


class PackingLimitError(ValueError):
    pass


def lift_rectangles(payloads, profile, tasks):
    rectangles=[(profile.get('operator_length_m',.6),profile.get('operator_width_m',.6),
                 profile.get('operator_height_m',1.8),True,'Person')]
    for task in tasks:
        payload=payloads[task.payload]
        length,width,height=payload.length_m,payload.width_m,payload.height_m
        orientations=getattr(payload,'allowed_carry_orientations',['lengthways','sideways'])
        if 'lengthways' not in orientations and 'sideways' in orientations:length,width=width,length
        rotate='lengthways' in orientations and 'sideways' in orientations
        rectangles.extend((length,width,height,rotate,task.payload) for _ in range(max(1,int(task.quantity))))
    return tuple(rectangles)


@lru_cache(maxsize=8192)
def pack_lift(length,width,height,rectangles):
    """Return immutable placements, None for proven failure, or a search limit.

    Try item order, permitted rotations and edge-aligned positions. Floor area,
    height and overlap are checked explicitly; no loads are stacked. A bounded
    search exhaustion is reported separately from an impossible fit.
    """
    eps=1e-9
    if any(r[2]>height+eps for r in rectangles):return None
    if sum(r[0]*r[1] for r in rectangles)>length*width+eps:return None
    def orientations(r):
        values=[(r[0],r[1],False)]
        if r[3] and r[0]!=r[1]:values.append((r[1],r[0],True))
        return [(l,w,turned) for l,w,turned in values if l<=length+eps and w<=width+eps]
    options=[orientations(r) for r in rectangles]
    if any(not values for values in options):return None
    visited=set();budget=10000
    def place(remaining,placed):
        nonlocal budget
        if not remaining:return tuple(placed)
        budget-=1
        if budget<0:raise PackingLimitError('Lift arrangement search limit reached; review carrying capacity or the load arrangement.')
        signature=(remaining,tuple(sorted((x,y,l,w) for _,x,y,l,w,_ in placed)))
        if signature in visited:return None
        visited.add(signature)
        xs=sorted({0.0,*[x+l for _,x,y,l,w,_ in placed]})
        ys=sorted({0.0,*[y+w for _,x,y,l,w,_ in placed]})
        tried=set()
        for index in sorted(remaining,key=lambda i:(-rectangles[i][0]*rectangles[i][1],i)):
            shape=rectangles[index][:4]
            if shape in tried:continue
            tried.add(shape)
            for l,w,turned in options[index]:
                for y in ys:
                    if y+w>width+eps:continue
                    for x in xs:
                        if x+l>length+eps:continue
                        if any(x<px+pl-eps and x+l>px+eps and y<py+pw-eps and y+w>py+eps
                               for _,px,py,pl,pw,_ in placed):continue
                        found=place(tuple(i for i in remaining if i!=index),placed+[(index,x,y,l,w,turned)])
                        if found is not None:return found
        return None
    return place(tuple(range(len(rectangles))),[])
