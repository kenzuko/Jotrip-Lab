import assert from 'node:assert/strict';
import test from 'node:test';
import { buildSummary, normalizeRecords, runQualityChecks } from './normalize.mjs';

test('collapses VASCO and Vietnam Airlines codeshare into one physical movement', () => {
  const raw = [
    {
      direction: 'departure',
      flight_number: '0V8074',
      times: ['18:35'],
      status: 'ĐÃ CẤT CÁNH',
      context: '10 | ĐÃ CẤT CÁNH | 44 | 0V8074 • VASCO | VN8074 | CAN THO | 18:35 | 17'
    },
    {
      direction: 'departure',
      flight_number: 'VN8074',
      times: ['18:35'],
      status: 'ĐÃ CẤT CÁNH',
      context: 'ĐÃ CẤT CÁNH | 44 | 0V8074 • VASCO | VN8074 | CAN THO | 18:35 | 17 | 12'
    }
  ];
  const records = normalizeRecords(raw, '2026-09-15');
  assert.equal(records.length, 1);
  assert.equal(records[0].operating_flight_number, '0V8074');
  assert.deepEqual(records[0].marketing_flight_numbers, ['VN8074']);
  assert.equal(records[0].station, 'CAN THO');
  assert.equal(records[0].market, 'domestic');
});

test('skips multiple codeshare numbers before the real station', () => {
  const records = normalizeRecords([{
    direction: 'departure',
    flight_number: 'VN3414',
    times: ['09:20'],
    status: 'ĐÚNG GIỜ',
    context: 'ĐÚNG GIỜ | 12 | VN3414 • VIETNAM AIRLINES | VN3414-DL7866 | HO CHI MINH | 09:20 | 4'
  }], '2026-09-15');
  assert.equal(records[0].station, 'HO CHI MINH');
  assert.deepEqual(records[0].marketing_flight_numbers, ['DL7866']);
});

test('summary counts physical movements after normalization', () => {
  const records = normalizeRecords([
    {
      direction: 'arrival', flight_number: 'VJ123', times: ['08:00'], status: 'ĐÚNG GIỜ',
      context: 'ĐÚNG GIỜ | 1 | VJ123 • VIETJET AIR | HA NOI | 08:00'
    },
    {
      direction: 'departure', flight_number: '0V8074', times: ['18:35'], status: 'ĐÚNG GIỜ',
      context: 'ĐÚNG GIỜ | 2 | 0V8074 • VASCO | VN8074 | CAN THO | 18:35'
    },
    {
      direction: 'departure', flight_number: 'VN8074', times: ['18:35'], status: 'ĐÚNG GIỜ',
      context: 'ĐÚNG GIỜ | 2 | 0V8074 • VASCO | VN8074 | CAN THO | 18:35'
    }
  ], '2026-09-15');
  assert.deepEqual(buildSummary(records).counts, { arrivals: 1, departures: 1, total: 2 });
});

test('QA rejects unknown station labels instead of misclassifying them', () => {
  const records = normalizeRecords([{
    direction: 'arrival', flight_number: 'VJ123', times: ['08:00'], status: 'ĐÚNG GIỜ',
    context: 'ĐÚNG GIỜ | 1 | VJ123 • VIETJET AIR | VN9999 | 08:00'
  }], '2026-09-15');
  const qa = runQualityChecks(records);
  assert.equal(qa.passed, false);
  assert.ok(qa.errors.some(error => error.startsWith('MISSING_STATION:')));
});
