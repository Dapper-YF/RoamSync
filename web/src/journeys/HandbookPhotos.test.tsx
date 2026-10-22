import {expect, it} from 'vitest';
import {matchingIllustration} from './HandbookPhotos';
const park = {name: '人民公园', location: {longitude: 104.057641, latitude: 30.65699}};
const items = [park] as Parameters<typeof matchingIllustration>[0];
it('requires canonical identity and coordinates for activity imagery', () => {
  expect(matchingIllustration(items, '人民公园', [104.057641, 30.65699])).toBe(park);
  expect(matchingIllustration(items, '人民公园', [120, 30])).toBeUndefined();
  expect(matchingIllustration(items, '茶艺体验', [104.057641, 30.65699])).toBeUndefined();
  expect(matchingIllustration(items, '人民公园')).toBeUndefined();
});
it('allows a labeled destination image without claiming an activity match', () => {
  expect(matchingIllustration(items)).toBe(park);
  expect(matchingIllustration([])).toBeUndefined();
});
