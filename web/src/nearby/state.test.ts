import { describe, expect, it } from "vitest";
import { distanceMeters, wgs84ToGcj02 } from "./state";
describe("nearby coordinate boundary", () => {
  it("converts browser WGS84 rather than sending it to AMap unchanged", () => {
    const result = wgs84ToGcj02(116.397, 39.908);
    expect(result.coordinate_system).toBe("gcj02");
    expect(result.longitude).toBeCloseTo(116.40324, 4);
    expect(result.latitude).toBeCloseTo(39.9094, 4);
    expect(distanceMeters({ longitude: 116.397, latitude: 39.908, coordinate_system: "gcj02" }, result)).toBeGreaterThan(500);
  });
  it.each([[NaN,30], [181,30], [104,91], [0,0], [-73,40]])("rejects invalid or unsupported location %s,%s", (longitude, latitude) => {
    expect(() => wgs84ToGcj02(longitude, latitude)).toThrow();
  });
  it("distance is symmetric and does not treat a nearby point as the same location", () => {
    const a = { longitude:104.057641, latitude:30.65699, coordinate_system:"gcj02" as const };
    const b = { longitude:104.067641, latitude:30.65699, coordinate_system:"gcj02" as const };
    expect(distanceMeters(a,a)).toBe(0);
    expect(distanceMeters(a,b)).toBe(distanceMeters(b,a));
    expect(distanceMeters(a,b)).toBeGreaterThan(900);
    expect(distanceMeters(a,b)).toBeLessThan(1000);
  });
});
