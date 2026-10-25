import {useEffect, useState} from 'react';
import type {CanonicalPlaceRef, Coordinates} from '../domain/types';
import {approvedPhotos, type ContentPlace} from '../data/placeContentRepository';
import {PlaceCover} from '../components/PlacePhotos';
import {SearchImage, type AnswerSearch} from '../components/AssistantAnswer';
import './HandbookPhotos.css';

type Illustration = Pick<ContentPlace, 'ref' | 'name' | 'city' | 'location' | 'images'>;
const cache = new Map<string, Promise<Illustration[]>>();

export function matchingIllustration(items: Illustration[], name?: string, coordinates?: Coordinates, placeRef?: CanonicalPlaceRef | null) {
  if (!name && !placeRef) return items[0];
  if (!placeRef) return undefined;
  return items.find(p => p.ref.place_id === placeRef.place_id &&
    p.ref.external_ref.provider === placeRef.external_ref.provider &&
    p.ref.external_ref.provider_place_id === placeRef.external_ref.provider_place_id &&
    (!coordinates || (Math.abs(p.location.longitude - coordinates[0]) < .002 &&
      Math.abs(p.location.latitude - coordinates[1]) < .002)));
}

export function HandbookPhoto({city, name, coordinates, placeRef}: {city: string; name?: string; coordinates?: Coordinates; placeRef?: CanonicalPlaceRef | null}) {
  const key = JSON.stringify([city,name,coordinates,placeRef]);
  const [loaded, setLoaded] = useState<{key:string; place?:Illustration; reference?:AnswerSearch['images'][number]}>();
  const placeId=placeRef?.place_id, provider=placeRef?.external_ref.provider, providerId=placeRef?.external_ref.provider_place_id;
  const longitude=coordinates?.[0], latitude=coordinates?.[1];
  useEffect(() => {
    let active = true;
    const cityKey = city.trim().replace(/市$/, '');
    if (!cache.has(cityKey)) {
      const request = fetch(`/api/v1/media/place-images?${new URLSearchParams({city: cityKey})}`, {signal:AbortSignal.timeout(6000)})
        .then(async r => {
          if (!r.ok) throw new Error('Image catalog unavailable');
          const data = await r.json() as {items: Illustration[]};
          return data.items.filter(p => p.city?.replace(/市$/, '') === cityKey);
        });
      cache.set(cityKey, request);
      void request.catch(() => { if (cache.get(cityKey) === request) cache.delete(cityKey); });
    }
    void (async()=>{
      const items=await cache.get(cityKey)!.catch(()=>[]);
      const ref=placeId && provider && providerId ? {place_id:placeId,external_ref:{provider,provider_place_id:providerId}} : undefined;
      const point:Coordinates|undefined=longitude!==undefined && latitude!==undefined ? [longitude,latitude] : undefined;
      const reviewed=matchingIllustration(items,name,point,ref);
      if(reviewed && approvedPhotos(reviewed.images,reviewed.ref.place_id,reviewed.ref.external_ref.provider_place_id).length){
        if(active)setLoaded({key,place:reviewed});
        return;
      }
      if(!active || !name || !ref)return;
      const response=await fetch(`/api/v1/places/${encodeURIComponent(ref.place_id)}/reference-images?${new URLSearchParams({provider_place_id:ref.external_ref.provider_place_id})}`, {signal:AbortSignal.timeout(22000)});
      if(!response.ok)return;
      const data=await response.json() as {status:string;place?:Illustration;images:AnswerSearch['images']};
      if(data.status!=='available' || !data.place || data.place.city?.replace(/市$/,'')!==cityKey || !matchingIllustration([data.place],name,point,ref))return;
      const reference=data.images.find(image=>image.usage_basis==='search_reference');
      if(active && reference)setLoaded({key,place:data.place,reference});
    })().catch(()=>{});
    return () => { active = false; };
  }, [city,name,placeId,provider,providerId,longitude,latitude,key]);
  const place = loaded?.key===key ? loaded.place : undefined;
  if (!place) return null;
  if(loaded?.reference)return <div className="handbook-activity-photo"><SearchImage key={loaded.reference.url} image={loaded.reference} placeName={place.name}/></div>;
  const photos = approvedPhotos(place.images, place.ref.place_id, place.ref.external_ref.provider_place_id);
  if (!photos.length) return null;
  return <div className={name ? 'handbook-activity-photo' : 'handbook-trip-cover'}>
    <PlaceCover photos={photos} full />
    {!name && <small>{place.name} · 目的地实景</small>}
  </div>;
}
