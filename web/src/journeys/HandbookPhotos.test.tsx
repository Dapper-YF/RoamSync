import {expect, it} from 'vitest';
import {matchingIllustration} from './HandbookPhotos';
const ref={place_id:'canonical-park',external_ref:{provider:'amap' as const,provider_place_id:'B001'}};
const park = {ref,name:'人民公园',location:{longitude:104.057641,latitude:30.65699}};
const items=[park] as Parameters<typeof matchingIllustration>[0];
it('requires exact canonical and provider identity for activity imagery',()=>{expect(matchingIllustration(items,'人民公园',[104.057641,30.65699],ref)).toBe(park);expect(matchingIllustration(items,'人民公园',[104.057641,30.65699])).toBeUndefined();expect(matchingIllustration(items,'人民公园',[104.057641,30.65699],{...ref,place_id:'another'})).toBeUndefined();expect(matchingIllustration(items,'人民公园',[104.057641,30.65699],{...ref,external_ref:{...ref.external_ref,provider_place_id:'another'}})).toBeUndefined();});
it('matches exact identity even when an activity has a custom title',()=>{expect(matchingIllustration(items,'茶艺体验',[104.057641,30.65699],ref)).toBe(park);});
it('allows a labeled destination image without claiming an activity match',()=>{expect(matchingIllustration(items)).toBe(park);expect(matchingIllustration([])).toBeUndefined();});

it('retains coordinate guards and rejects unbound custom or missing names',()=>{
  expect(matchingIllustration(items,'人民公园',[120,30],ref)).toBeUndefined();
  expect(matchingIllustration(items,'人民公园')).toBeUndefined();
  expect(matchingIllustration(items,'茶艺体验',[104.057641,30.65699])).toBeUndefined();
});
