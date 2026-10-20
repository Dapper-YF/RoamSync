import { fireEvent, render, screen, cleanup } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { PlaceCover, PlaceGallery } from './PlacePhotos';
import { approvedPhotos, type ContentImage } from '../data/placeContentRepository';

afterEach(cleanup);
const image: ContentImage = {url:'/api/v1/media/place-images/park-0-960.jpg', thumbnail_url:'/api/v1/media/place-images/park-0-480.jpg',
  title:'公园实景', source_url:'https://commons.wikimedia.org/wiki/File:Park.jpg', attribution:'Photographer',
  usage_basis:'reviewed_commons_license', provider:'wikimedia_commons', license_name:'CC BY-SA 4.0', license_url:'https://creativecommons.org/licenses/by-sa/4.0',
  place_ref:{place_id:'canonical',external_ref:{provider:'amap',provider_place_id:'EXACT'}}};
it('rejects wrong place, unreviewed license and arbitrary URLs', () => {
  expect(approvedPhotos([image], 'canonical', 'EXACT')).toHaveLength(1);
  expect(approvedPhotos([image], 'other')).toHaveLength(0);
  expect(approvedPhotos([image], 'canonical', 'OTHER')).toHaveLength(0);
  for (const bad of [{...image,license_url:''},{...image,url:'https://restricted.example/photo.jpg'},{...image,provider:null}])
    expect(approvedPhotos([bad], 'canonical')).toHaveLength(0);
});
it('keeps attribution and gracefully handles an image failing without hiding content', () => {
  render(<PlaceCover photos={approvedPhotos([image], 'canonical')}/>);
  const photo = screen.getByRole('img');
  expect(photo.getAttribute('loading')).toBe('lazy');
  fireEvent.error(photo);
  expect(screen.getByRole('status').textContent).toContain('地点信息仍可使用');
  fireEvent.click(screen.getByLabelText('图片来源与许可'));
  expect(screen.getByRole('link', {name:'CC BY-SA 4.0'}).getAttribute('href')).toBe(image.license_url);
});
it('browses multiple photos and shows their individual credits', () => {
  const photos = approvedPhotos([image, {...image,url:'/api/v1/media/place-images/park-1-960.jpg',title:'第二视角',attribution:'Another author'}], 'canonical');
  render(<PlaceGallery photos={photos} name="公园"/>);
  fireEvent.click(screen.getByRole('button',{name:'查看第2张照片'}));
  expect(screen.getByRole('img').getAttribute('alt')).toBe('第二视角');
  expect(screen.getByText(/Another author/)).not.toBeVisible();
  fireEvent.click(screen.getByLabelText('图片来源与许可'));
  expect(screen.getByRole('link',{name:/Another author/})).toBeVisible();
});
