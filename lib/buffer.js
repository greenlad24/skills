// Buffer API client (GraphQL, public beta) — free plan supports 3 connected
// channels, plenty for 1 Instagram + 1 Facebook page.
// Docs: https://developers.buffer.com (personal API key: Buffer → Settings → API)
const API = 'https://api.buffer.com';

async function gql(apiKey, query, variables) {
  if (!apiKey) throw new Error('Buffer API key is missing — add it in Settings.');
  const res = await fetch(API, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query, variables }),
  });
  const text = await res.text();
  let json;
  try { json = JSON.parse(text); } catch { json = null; }
  if (!res.ok) {
    throw new Error(`Buffer: ${json?.errors?.[0]?.message || text.slice(0, 300) || `HTTP ${res.status}`}`);
  }
  if (json?.errors?.length) {
    throw new Error(`Buffer: ${json.errors.map((e) => e.message).join('; ')}`);
  }
  return json.data;
}

/** List every channel across the account's organizations. */
async function listChannels(apiKey) {
  const acct = await gql(apiKey, `query { account { organizations { id name } } }`);
  const orgs = acct?.account?.organizations || [];
  if (!orgs.length) throw new Error('Buffer: no organizations found on this account.');
  const channels = [];
  for (const org of orgs) {
    const data = await gql(
      apiKey,
      `query GetChannels($orgId: OrganizationId!) {
        channels(input: { organizationId: $orgId }) { id name displayName service }
      }`,
      { orgId: org.id }
    );
    for (const c of data?.channels || []) {
      channels.push({
        id: c.id,
        name: c.displayName || c.name || '',
        identifier: c.service || '',
        organizationId: org.id,
      });
    }
  }
  return channels;
}

/**
 * Create a post on one channel, published automatically at dueAt (ISO UTC).
 * imageUrl must be publicly reachable (Buffer's servers download it).
 */
async function createPost(apiKey, { channelId, text, imageUrl, dueAt }) {
  const data = await gql(
    apiKey,
    `mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        __typename
        ... on PostActionSuccess { post { id dueAt } }
        ... on MutationError { message }
      }
    }`,
    {
      input: {
        channelId,
        text,
        schedulingType: 'automatic',
        mode: 'customScheduled',
        dueAt,
        assets: imageUrl ? [{ image: { url: imageUrl } }] : [],
      },
    }
  );
  const result = data?.createPost;
  if (!result || result.__typename === 'MutationError') {
    throw new Error(`Buffer createPost: ${result?.message || 'unknown error'}`);
  }
  return result.post;
}

module.exports = { listChannels, createPost };
