import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { ExplorePhoto } from '../domain/explore';
import './PlacePhotos.css';

function Credit({ photo }: { photo: ExplorePhoto }) {
  return <figcaption className="place-photo-credit"><details><summary aria-label="图片来源与许可">ⓘ</summary><div>{photo.title}<br/><a href={photo.source_url} target="_blank" rel="noreferrer">{photo.attribution} · Wikimedia Commons</a>{' · '}<a href={photo.license_url} target="_blank" rel="noreferrer">{photo.license_name}</a><span> · {photo.changes}</span><p>历史照片，不代表当前天气、营业状态或现场情况。</p></div></details></figcaption>;
}
function Photo({ photo, full = false }: { photo: ExplorePhoto; full?: boolean }) {
  const [failed, setFailed] = useState(false);
  return failed ? <div className="place-photo-missing" role="status">照片暂时无法加载 · 地点信息仍可使用</div> : <img src={full ? photo.url : photo.thumbnail_url || photo.url} alt={photo.title} loading="lazy" decoding="async" referrerPolicy="no-referrer" onError={() => setFailed(true)} />;
}
export function PlaceCover({ photos, to, onOpen, full = false }: { photos: ExplorePhoto[]; to?: string; onOpen?: () => void; full?: boolean }) {
  if (!photos.length) return null; // Keep the accepted compact no-photo card.
  return <figure className="place-photo-cover">{to ? <Link to={to} onClick={onOpen} aria-label={`查看${photos[0].title}`}><Photo key={photos[0].url} photo={photos[0]} full={full} /></Link> : <Photo key={photos[0].url} photo={photos[0]} full={full} />}<Credit photo={photos[0]} /></figure>;
}
export function PlaceGallery({ photos, name }: { photos: ExplorePhoto[]; name: string }) {
  const [index, setIndex] = useState(0);
  if (!photos.length) return null;
  const selected = photos[index] ?? photos[0];
  return <section className="place-photo-gallery" aria-label={`${name}的地点照片`}><figure><Photo key={selected.url} photo={selected} full /><Credit photo={selected} /></figure>{photos.length > 1 && <nav aria-label="选择地点照片">{photos.map((photo, i) => <button key={photo.url} type="button" aria-label={`查看第${i+1}张照片`} aria-pressed={index === i} onClick={() => setIndex(i)}>{i+1}</button>)}<small>{Math.min(index+1, photos.length)} / {photos.length}</small></nav>}</section>;
}
