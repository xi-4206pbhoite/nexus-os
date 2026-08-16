/**
 * Single source of truth for every word on the landing page.
 *
 * Content discipline: NEXUS OS sells on "never invent a number". This page is
 * held to the same rule — no invented customer counts, logos, testimonials or
 * results. Every figure below either comes from the source documents or is
 * explicitly labelled illustrative in the UI that renders it.
 */

export const site = {
  name: 'NEXUS OS',
  tagline: 'Your AI executive team. Built around your company.',
  description:
    'NEXUS OS learns your company once, then tells you what changed, what it means, what to do about it — and does the work. One Company Brain, seven AI directors, every number traceable to a real source.',
  url: 'https://nexusos.example',
  region: 'Oman & the GCC',
} as const

export const nav = [
  { label: 'The loop', href: '#loop' },
  { label: 'Company Brain', href: '#brain' },
  { label: 'Your team', href: '#team' },
  { label: 'Capabilities', href: '#pillars' },
  { label: 'Trust', href: '#trust' },
  { label: 'Pricing', href: '#pricing' },
] as const

export const hero = {
  eyebrow: 'AI Business Operating System',
  headlineTop: 'Your AI',
  headlineAccent: 'executive team.',
  headlineBottom: 'Built around your company.',
  sub: 'Connect your website, documents and tools once. NEXUS learns how your business works, tells you what needs attention, helps you decide — and does the work.',
  primaryCta: 'Start the 7-minute audit',
  secondaryCta: 'See how it works',
  note: 'Built for Oman and the wider GCC — OMR/AED/SAR, regional business norms, Arabic on the roadmap.',
  ticker: [
    'One Company Brain',
    'Seven AI directors',
    'Every number traceable',
    'GCC-native',
    'Decisions, not dashboards',
  ],
} as const

/** Section 2 — the problem. Straight from the solution-offering doc. */
export const problem = {
  eyebrow: 'The problem',
  headline: 'A growing business is expected to operate like a large one.',
  sub: 'The owner is the strategist, the marketer, the analyst and the closer. Every available option is bad in a different way.',
  options: [
    {
      option: 'Hire an executive team',
      why: 'Several senior salaries before a single result lands.',
      icon: 'team',
    },
    {
      option: 'Buy 5–6 SaaS tools',
      why: 'High combined cost, six logins, six data silos, none of them talk.',
      icon: 'stack',
    },
    {
      option: 'Hire an agency',
      why: 'Good output, no institutional memory. It stops when the retainer stops.',
      icon: 'agency',
    },
    {
      option: 'Use ChatGPT directly',
      why: "Generic advice — it doesn't know your prices, customers or competitors.",
      icon: 'chat',
    },
    {
      option: 'Do nothing',
      why: 'Decisions made on instinct. Problems found after they cost money.',
      icon: 'nothing',
    },
  ],
  punchline: {
    before: 'Every existing AI tool answers',
    quiet: '“what happened?”',
    after: 'Nobody answers',
    loud: '“what should I do about it?”',
    tail: '— and then does it.',
  },
} as const

/** Section 3 — the five-stage loop. This is the product. */
export const loop = {
  eyebrow: 'How it works',
  headline: 'One loop, running continuously.',
  sub: 'Anything that does not close this loop is a feature. The loop itself is the product.',
  steps: [
    {
      id: 'connect',
      n: '01',
      title: 'Connect',
      lead: 'Your website, tools and knowledge.',
      body: 'An 11-step guided setup. Website scan, document upload, Google Analytics, Search Console, your CRM and competitors — connected once.',
      chips: ['Website scan', 'Documents', 'GA4', 'Search Console', 'Competitors'],
    },
    {
      id: 'understand',
      n: '02',
      title: 'Understand',
      lead: 'NEXUS learns your company into a permanent Company Brain.',
      body: 'Your services, prices, ideal customer, brand voice, goals and competitors become structured, retrievable knowledge — with every fact showing where it came from.',
      chips: ['Company Brain', 'RAG index', 'Brand voice', 'Source-tagged facts'],
    },
    {
      id: 'decide',
      n: '03',
      title: 'Decide',
      lead: 'It identifies the risks, opportunities and decisions in front of you.',
      body: 'A daily brief of what actually changed, a health score per department, and decision cards you can approve, question or dismiss inside the product.',
      chips: ['Morning Brief', 'Health Score', 'Decision cards', 'Risk register'],
    },
    {
      id: 'execute',
      n: '04',
      title: 'Execute',
      lead: 'It creates the strategy, content, proposals and tasks.',
      body: 'A full 90-day growth plan, content in your brand voice, and client-ready proposals priced from your own uploaded price list — not a template.',
      chips: ['Growth Planner', 'Content Studio', 'Proposal Studio', 'SEO briefs'],
    },
    {
      id: 'improve',
      n: '05',
      title: 'Improve',
      lead: 'It measures the result and adapts next week’s advice.',
      body: 'Scores are recomputed on a schedule and history is kept, so progress is visible and the advice compounds instead of resetting.',
      chips: ['Score history', 'Week-over-week deltas', 'Audit trail'],
    },
  ],
} as const

/** Section 4 — the moat. */
export const brain = {
  eyebrow: 'The difference',
  headline: 'Seven directors. One Company Brain.',
  sub: 'The Sales Director already knows what the Finance Advisor knows. This is not a bundle of chatbots — it is one shared understanding of your business, viewed seven ways.',
  points: [
    {
      title: 'It learns once, then never forgets',
      body: 'Every document you upload, every decision you record and every week of history makes the next answer better than the last.',
    },
    {
      title: 'It gets harder to leave on its own',
      body: 'A feature is copyable in a weekend. Your accumulated business context is not — and it compounds every week you use it.',
    },
    {
      title: 'It reasons across the whole business',
      body: 'Point tools see one channel each. NEXUS connects a traffic drop to a stalled deal to a competitor’s new campaign — because it can see all three.',
    },
  ],
  nodes: [
    { label: 'Website', angle: -90 },
    { label: 'Documents', angle: -30 },
    { label: 'CRM', angle: 30 },
    { label: 'Analytics', angle: 90 },
    { label: 'Competitors', angle: 150 },
    { label: 'Accounting', angle: 210 },
  ],
} as const

/** Section 5 — the seven AI directors. */
export const directors = {
  eyebrow: 'Your AI executive team',
  headline: 'Seven directors, on staff from day one.',
  sub: 'Each one owns a function. All seven read from the same brain.',
  list: [
    {
      name: 'Chief of Staff',
      owns: 'Daily executive brief, priorities, risks, cross-department recommendations',
      accent: 'gold',
    },
    {
      name: 'Marketing Director',
      owns: 'Strategy, campaign planning, content calendar, SEO, brand positioning',
      accent: 'steel',
    },
    {
      name: 'Sales Director',
      owns: 'Pipeline, lead intelligence, forecasting, proposals, follow-ups',
      accent: 'clay',
    },
    {
      name: 'Finance Advisor',
      owns: 'Revenue and margin analysis, cash-flow signals, budget scenarios, pricing',
      accent: 'ink',
    },
    {
      name: 'HR Director',
      owns: 'Policies, recruitment plans, onboarding, training, team capacity',
      accent: 'slate',
    },
    {
      name: 'Operations Director',
      owns: 'SOPs, workflow analysis, bottlenecks, task management',
      accent: 'steel',
    },
    {
      name: 'Strategy Director',
      owns: 'Expansion planning, market entry, business simulation, risk assessment',
      accent: 'gold',
    },
  ],
} as const

/** Section 6 — seven capability pillars, as a Pinterest-style bento grid. */
export const pillars = {
  eyebrow: 'Seven pillars',
  headline: 'Everything the business needs, in one place.',
  sub: 'Organised by outcome, not by tool.',
  list: [
    {
      title: 'Executive Command',
      promise: 'Know what changed, why it matters, and what to do next.',
      items: ['CEO Morning Brief', 'Company Health Score', 'Opportunity Radar', 'Decision Assistant', 'Business Simulator'],
      span: 'lg',
      tone: 'ink',
    },
    {
      title: 'Growth & Marketing',
      promise: 'Plan, launch and optimise growth from one workspace.',
      items: ['AI Marketing Director', 'Content & Campaign Calendar', 'SEO Intelligence', 'Brand Intelligence', 'Pricing Intelligence'],
      span: 'md',
      tone: 'gold',
    },
    {
      title: 'Sales & Revenue',
      promise: 'Find the right opportunities and move them toward revenue.',
      items: ['Lead Intelligence', 'Sales Workspace & CRM', 'Proposal Studio', 'Communication Intelligence', 'Revenue Forecasting'],
      span: 'md',
      tone: 'clay',
    },
    {
      title: 'Competitive Intelligence',
      promise: 'Know who your competitors are, what they are doing, and how to respond.',
      items: ['Competitor Discovery', 'Advertisement Tracking', 'SEO Gap Analysis', 'Alerts', 'Market Positioning'],
      span: 'md',
      tone: 'steel',
    },
    {
      title: 'Customers & Retention',
      promise: 'Identify customers at risk before the revenue disappears.',
      items: ['Customer Health', 'Churn Prediction', 'Review Monitoring', 'Retention Campaigns', 'Revenue at Risk'],
      span: 'md',
      tone: 'slate',
    },
    {
      title: 'People & Operations',
      promise: 'Preserve knowledge and keep the company running consistently.',
      items: ['Company Brain', 'SOP Builder', 'Workflow Automation', 'Team Capacity', 'Company Memory'],
      span: 'md',
      tone: 'steel',
    },
    {
      title: 'Finance & Strategic Decisions',
      promise: 'Test major decisions before committing money and resources.',
      items: ['Financial Health', 'Margin Analysis', 'Pricing & Expansion Simulator', 'Scenario Planning', 'Risk Register'],
      span: 'lg',
      tone: 'ink',
    },
  ],
} as const

/** Section 7 — the three moments that sell the product. */
export const moments = {
  eyebrow: 'What it feels like',
  headline: 'Three moments.',
  sub: 'Not a demo. Your business.',
  list: [
    {
      when: 'Minute 7',
      title: 'The audit',
      body: 'Onboarding ends with a real assessment of your business — pages analysed, services identified, competitors detected, SEO gaps found, a digital maturity score.',
    },
    {
      when: 'Day 1',
      title: 'The morning brief',
      body: 'Six things that changed in the last seven days, and one recommended action that ties two of them together. This is the habit.',
    },
    {
      when: 'Week 4',
      title: 'The decision',
      body: 'A decision card with the reasoning, the data behind it and the risk level. Approve it, ask why, or dismiss it — inside the product.',
    },
  ],
} as const

/** Section 8 — trust. The engineering claim, not a marketing claim. */
export const trust = {
  eyebrow: 'Why you can believe it',
  headline: 'Never invent a number.',
  sub: 'The single reason AI business tools fail is that people stop believing the numbers. NEXUS is engineered around one rule — and it is enforced in code, not in a prompt.',
  rules: [
    {
      title: 'Fetched or calculated. Never guessed.',
      body: 'Every figure you see is pulled from a connected source or computed deterministically in code. The AI interprets and phrases; it does not estimate.',
    },
    {
      title: 'Confidence is computed, not written.',
      body: 'Confidence percentages, financial exposure and churn risk come from defined formulas in the backend. A language model never produces the figure.',
    },
    {
      title: 'Every proposal price is cited.',
      body: 'Prices are retrieved from your own uploaded price list with a reference to the document and page. If a price is not found, you get a visible placeholder — never a plausible number.',
    },
    {
      title: 'Missing data shows as missing.',
      body: 'No connected analytics means the marketing score says so. You get a visible gap and a prompt to connect the source, not a confident-sounding guess.',
    },
    {
      title: 'Every card can answer “why?”',
      body: 'Each insight stores the input data and the calculation behind it, so any recommendation can show its working.',
    },
  ],
  pipeline: [
    { step: 'Fetch real inputs', note: 'gaps recorded explicitly' },
    { step: 'Compute in code', note: 'scores, deltas, exposure' },
    { step: 'Ground the prompt', note: 'company context + data block' },
    { step: 'Validate the output', note: 'schema-checked, retried' },
    { step: 'Store the trace', note: 'auditable forever' },
  ],
} as const

/** Section 9 — competitive position. */
export const compare = {
  eyebrow: 'Why NEXUS',
  headline: 'The difference is structural.',
  rows: [
    { dimension: 'Scope of knowledge', them: 'One channel each', us: 'Whole business, one brain' },
    { dimension: 'Output', them: 'Reports and dashboards', us: 'Decisions plus the executed work' },
    { dimension: 'Personalisation', them: 'Templates', us: 'Your prices, customers, competitors, voice' },
    { dimension: 'Regional fit', them: 'US / EU norms', us: 'GCC norms, OMR/AED/SAR, Arabic on the roadmap' },
    { dimension: 'Cost', them: '5–6 subscriptions', us: 'One' },
    { dimension: 'Memory', them: 'None across tools', us: 'Permanent, compounding Company Brain' },
  ],
  themLabel: 'Point tools',
  usLabel: 'NEXUS OS',
} as const

/** Section 10 — packaging. Prices are indicative per the source material. */
export const pricing = {
  eyebrow: 'Packaging',
  headline: 'Three tiers. One subscription.',
  sub: 'Free trial, monthly billing, upgrade or downgrade any time, cancel any time. AI usage is our operating cost — never billed to you per generation.',
  disclaimer:
    'Indicative packaging. Pricing is being validated with design-partner customers before launch — talk to us and it will be honest about where it stands.',
  tiers: [
    {
      name: 'Starter',
      price: '$49',
      cadence: '/month',
      for: 'Small teams proving the value',
      cta: 'Start free trial',
      featured: false,
      includes: [
        'Company Brain & onboarding audit',
        'Morning Brief & Health Score',
        'CRM & pipeline',
        'Growth Planner & Content Studio',
        'Proposal Studio (limited)',
      ],
      excludes: ['SEO Intelligence', 'Competitor War Room', 'Lead Intelligence'],
    },
    {
      name: 'Growth',
      price: "Let's talk",
      cadence: '',
      for: 'The core product',
      cta: 'Book a walkthrough',
      featured: true,
      includes: [
        'Everything in Starter',
        'Proposal Studio (full RAG)',
        'SEO Intelligence',
        'Competitor War Room',
        'Lead Intelligence',
        'Customer Intelligence & churn',
        'Guided onboarding',
      ],
      excludes: ['Finance Advisor', 'Business Simulator'],
    },
    {
      name: 'Enterprise',
      price: "Let's talk",
      cadence: '',
      for: 'Multi-brand / multi-division',
      cta: 'Talk to us',
      featured: false,
      includes: [
        'Everything in Growth',
        'Finance Advisor & accounting sync',
        'Business Simulator & Decision Intelligence',
        'Multiple workspaces / divisions',
        'White-glove onboarding',
        'Custom integrations',
      ],
      excludes: [],
    },
  ],
} as const

export const faq = {
  eyebrow: 'Questions',
  headline: 'The things people ask first.',
  items: [
    {
      q: 'How is this different from just using ChatGPT?',
      a: 'ChatGPT does not know your prices, your customers, your competitors or your brand voice — so it gives you generic advice you have to translate yourself. NEXUS learns your business once into a Company Brain, and every answer is grounded in your real connected data. It also does not stop at advice: the recommendation ends in an action you can take inside the product.',
    },
    {
      q: 'What happens on day one if I have almost no data?',
      a: 'The onboarding audit is designed to work from your website alone, so you get a real assessment before connecting anything. Where a data source is missing, NEXUS shows a visible gap and asks you to connect it — it will not fill the space with a plausible guess. The product gets meaningfully better as you connect more.',
    },
    {
      q: 'Can I trust the numbers it shows me?',
      a: 'Every figure is either fetched from a connected source or calculated deterministically in our own code — never produced by a language model. Confidence percentages and financial exposure are computed from defined formulas. Every insight stores the data and calculation behind it, so any card can show its working.',
    },
    {
      q: 'Where does my data live, and is it used to train AI models?',
      a: 'Your documents are never used to train third-party models, and that is a contractual commitment rather than a policy page. Data is encrypted in transit and at rest, tenants are hard-isolated at the database layer, and we document exactly which region your data and embeddings are stored in.',
    },
    {
      q: 'Do you scrape LinkedIn for leads?',
      a: 'No. Lead sourcing is built on web search, Google Search and Maps, and public business directories. We do not scrape any platform whose terms prohibit it. If LinkedIn-sourced data is needed later, the compliant path is their official API partner programme.',
    },
    {
      q: 'Is it available in Arabic?',
      a: 'English at launch, with the architecture built for Arabic generation and right-to-left layout. Regional fit is already there from day one — OMR/AED/SAR currency, GCC business norms and regional data sources.',
    },
  ],
} as const

export const finalCta = {
  headline: 'Seven minutes from now, you could be reading an honest audit of your own business.',
  sub: 'Connect your website. NEXUS does the rest.',
  primary: 'Start the 7-minute audit',
  secondary: 'Book a walkthrough',
  reassure: 'No card required for the trial · Cancel any time',
} as const

export const footer = {
  blurb:
    'An AI business operating system for growing companies in Oman and the GCC. One Company Brain, seven AI directors, and every number traceable to a real source.',
  columns: [
    {
      title: 'Product',
      links: [
        { label: 'The loop', href: '#loop' },
        { label: 'Company Brain', href: '#brain' },
        { label: 'AI directors', href: '#team' },
        { label: 'Capabilities', href: '#pillars' },
        { label: 'Pricing', href: '#pricing' },
      ],
    },
    {
      title: 'Company',
      links: [
        { label: 'About', href: '#' },
        { label: 'Design partners', href: '#' },
        { label: 'Careers', href: '#' },
        { label: 'Contact', href: '#' },
      ],
    },
    {
      title: 'Trust',
      links: [
        { label: 'How grounding works', href: '#trust' },
        { label: 'Security', href: '#' },
        { label: 'Privacy', href: '#' },
        { label: 'Terms', href: '#' },
      ],
    },
  ],
  legal: 'Product in active development. Figures shown in product illustrations are illustrative, not measured results.',
} as const
