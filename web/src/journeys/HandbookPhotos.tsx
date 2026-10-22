import {useEffect,useState} from 'react';
import type {ExplorePlace} from '../domain/explore';
import {PlaceContentRepository} from '../data/placeContentRepository';
import {PlaceCover} from '../components/PlacePhotos';
const repo=new PlaceContentRepository();
const cache=new Map<string,Promise<ExplorePlace|undefined>>();
export function HandbookPhoto({city,name}:{city:string;name?:string}){
 const [place,setPlace]=useState<ExplorePlace>();
 useEffect(()=>{let active=true;setPlace(undefined);const key=`${city}:${name||''}`;if(!cache.has(key))cache.set(key,repo.search({city,q:name||'',category:'sight'}).then(r=>r.items.find(p=>p.city.replace(/市$/,'')===city.replace(/市$/,'')&&(!name||p.name===name)&&p.photos.length>0)).catch(()=>undefined));void cache.get(key)!.then(p=>{if(active)setPlace(p)});return()=>{active=false}},[city,name]);
 if(!place)return null;
 return <div className={name?'handbook-activity-photo':'handbook-trip-cover'}><PlaceCover photos={place.photos}/>{!name&&<small>{place.name} · 目的地影像</small>}</div>;
}
