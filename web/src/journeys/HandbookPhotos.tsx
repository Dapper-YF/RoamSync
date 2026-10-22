import {useEffect, useState} from 'react';
import type {Coordinates} from '../domain/types';
import {approvedPhotos, type ContentPlace} from '../data/placeContentRepository';
import {PlaceCover} from '../components/PlacePhotos';

type Illustration = Pick<ContentPlace, 'ref' | 'name' | 'city' | 'location' | 'images'>;
const cache = new Map<string, Promise<Illustration[]>>();

export function matchingIllustration(items: Illustration[], name?: string, coordinates?: Coordinates) {
  if (!name) return items[0];
  // Custom titles and other same-named parks cannot borrow a photo.
  return items.find(p => p.name === name && coordinates &&
    Math.abs(p.location.longitude - coordinates[0]) < .002 &&
    Math.abs(p.location.latitude - coordinates[1]) < .002);
}

export function HandbookPhoto({city, name, coordinates}: {city: string; name?: string; coordinates?: Coordinates}) {
  const [items, setItems] = useState<Illustration[]>([]);
  useEffect(() => {
    let active = true;
    setItems([]);
    const key = city.trim().replace(/市$/, '');
    if (!cache.has(key)) {
      const request = fetch(`/api/v1/media/place-images?${new URLSearchParams({city: key})}`)
        .then(async r => {
          if (!r.ok) throw new Error('Image catalog unavailable');
          const data = await r.json() as {items: Illustration[]};
          return data.items.filter(p => p.city?.replace(/市$/, '') === key);
        });
      cache.set(key, request);
      void request.catch(() => { if (cache.get(key) === request) cache.delete(key); });
    }
    void cache.get(key)!.then(data => { if (active) setItems(data); }).catch(() => {});
    return () => { active = false; };
  }, [city]);
  const place = matchingIllustration(items, name, coordinates);
  if (!place) return null;
  const photos = approvedPhotos(place.images, place.ref.place_id, place.ref.external_ref.provider_place_id);
  if (!photos.length) return null;
  return <div className={name ? 'handbook-activity-photo' : 'handbook-trip-cover'}>
    <PlaceCover photos={photos} full />
    {!name && <small>{place.name} · 目的地实景</small>}
  </div>;
}
