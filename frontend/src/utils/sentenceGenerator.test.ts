import { describe, expect, it } from 'vitest';
import { formatScheduleDays, generateRuleSentence } from './sentenceGenerator';
import type { RegisteredActionSpec } from '../types';

describe('sentenceGenerator', () => {
  describe('formatScheduleDays', () => {
    it('formats 7 days as Daily', () => {
      expect(formatScheduleDays(['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'])).toBe('Daily');
    });

    it('formats 6 days Monday to Saturday as Mon-Sat', () => {
      expect(formatScheduleDays(['mon', 'tue', 'wed', 'thu', 'fri', 'sat'])).toBe('Mon-Sat');
    });

    it('formats 5 weekdays Monday to Friday as Mon-Fri', () => {
      expect(formatScheduleDays(['mon', 'tue', 'wed', 'thu', 'fri'])).toBe('Mon-Fri');
    });

    it('formats weekend as Sat-Sun', () => {
      expect(formatScheduleDays(['sat', 'sun'])).toBe('Sat-Sun');
    });

    it('formats custom days capitalized', () => {
      expect(formatScheduleDays(['mon', 'wed', 'fri'])).toBe('Mon, Wed, Fri');
    });

    it('handles empty or undefined days', () => {
      expect(formatScheduleDays([])).toBe('');
      expect(formatScheduleDays(undefined)).toBe('');
    });
  });

  describe('generateRuleSentence', () => {
    it('generates milestone A sentence: heavy vehicle staying 2s Mon-Sat 09:00-17:00 critical', () => {
      const spec: RegisteredActionSpec = {
        name: 'No heavy vehicles during college hours',
        subject: {
          kind: 'vehicle',
          where: [{ attr: 'heavy', op: 'eq', value: true }],
          min_box_px: 80,
        },
        trigger: {
          template: 'presence',
          min_seconds: 2,
        },
        confirm: { n_of_m: [4, 5], min_confidence: 0.6 },
        schedule: {
          days: ['mon', 'tue', 'wed', 'thu', 'fri', 'sat'],
          from: '09:00',
          to: '17:00',
          timezone: 'Asia/Kolkata',
        },
        response: {
          severity: 'critical',
          pre_roll_s: 15,
          hold_s: 20,
        },
      };

      const sentence = generateRuleSentence(spec, 'Loading bay');
      expect(sentence).toBe(
        "Raise a CRITICAL alert if a truck or bus stays in 'Loading bay' for 2 s, Mon-Sat 09:00-17:00."
      );
    });

    it('generates sentence for unregistered vehicle dwelling in parking zone', () => {
      const spec: RegisteredActionSpec = {
        name: 'Unregistered vehicle dwelling',
        subject: {
          kind: 'vehicle',
          where: [{ attr: 'registry_status', op: 'eq', value: 'unregistered' }],
        },
        trigger: {
          template: 'dwell',
          dwell_seconds: 60,
        },
        response: {
          severity: 'medium',
        },
      };

      const sentence = generateRuleSentence(spec, 'Visitor Parking');
      expect(sentence).toBe(
        "Raise a MEDIUM alert if an unregistered vehicle dwells in 'Visitor Parking' for longer than 60 s."
      );
    });

    it('generates sentence for line crossing zone', () => {
      const spec: RegisteredActionSpec = {
        name: 'Exit Gate Crossing',
        subject: {
          kind: 'vehicle',
        },
        trigger: {
          template: 'line_crossing',
        },
        response: {
          severity: 'low',
        },
      };

      const sentence = generateRuleSentence(spec, 'Exit Barrier');
      expect(sentence).toBe("Raise a LOW alert if a vehicle crosses line 'Exit Barrier'.");
    });

    it('generates sentence for person without visible ID card', () => {
      const spec: RegisteredActionSpec = {
        name: 'Person no ID card',
        subject: {
          kind: 'person',
          where: [{ attr: 'id_state', op: 'eq', value: 'not_wearing' }],
        },
        trigger: {
          template: 'presence',
          min_seconds: 1,
        },
        response: {
          severity: 'critical',
        },
      };

      const sentence = generateRuleSentence(spec, 'Main Turnstile');
      expect(sentence).toBe(
        "Raise a CRITICAL alert if a person without a visible ID card stays in 'Main Turnstile' for 1 s."
      );
    });

    it('includes active calendar dates when configured', () => {
      const spec: RegisteredActionSpec = {
        name: 'Exam Period Restriction',
        subject: { kind: 'vehicle' },
        trigger: { template: 'presence' },
        valid: {
          from_date: '2026-11-10',
          until_date: '2026-11-20',
        },
        response: { severity: 'medium' },
      };

      const sentence = generateRuleSentence(spec, 'Academic Block');
      expect(sentence).toBe(
        "Raise a MEDIUM alert if a vehicle enters 'Academic Block' (active 2026-11-10 to 2026-11-20)."
      );
    });
  });
});

