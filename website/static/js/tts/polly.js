const te = new TextEncoder();


function toHex(buffer) {
    const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
    let s = "";
    for (let i = 0; i < bytes.length; i++) {
        s += bytes[i].toString(16).padStart(2, "0");
    }
    return s;
}


async function sha256Hex(message) {
    const data = typeof message === "string" ? te.encode(message) : message;
    const hashBuffer = await crypto.subtle.digest("SHA-256", data);
    return toHex(hashBuffer);
}


async function hmacSha256(key, data) {
    // key: string or ArrayBuffer; data: string
    let rawKey;
    if (typeof key === "string") {
        rawKey = te.encode(key);
    } else {
        rawKey = key;
    }

    const cryptoKey = await crypto.subtle.importKey(
        "raw",
        rawKey,
        { name: "HMAC", hash: "SHA-256" },
        false,
        ["sign"]
    );

    const sig = await crypto.subtle.sign("HMAC", cryptoKey, te.encode(data));
    return sig; // ArrayBuffer
}


async function getSignatureKey(secretKey, dateStamp, regionName, serviceName) {
    const kDate        = await hmacSha256("AWS4" + secretKey, dateStamp);
    const kRegion    = await hmacSha256(kDate, regionName);
    const kService = await hmacSha256(kRegion, serviceName);
    const kSigning = await hmacSha256(kService, "aws4_request");
    return kSigning;
}


function toAmzDate(date) {
    // YYYYMMDDTHHMMSSZ (no millis)
    return date.toISOString().replace(/[:-]|\.\d{3}/g, "");
}


function toDateStamp(date) {
    // YYYYMMDD
    return date.toISOString().slice(0, 10).replace(/-/g, "");
}


async function pollySynthTTS(text, voiceId, outputFormat = "mp3") {

    // Get keys from inputs
    const accessKeyId = document.querySelector('input[name="pak"]').value.trim();
    const secretAccessKey = document.querySelector('input[name="psk"]').value.trim();

    if (!accessKeyId || !secretAccessKey) {
        throw new Error("Missing access key or secret key in inputs 'pak' or 'psk'");
    }

    const method = "POST";
    const region = "eu-west-2";
    const service = "polly";
    const host = `polly.${region}.amazonaws.com`;
    const endpoint = `https://${host}`;
    const canonicalUri = "/v1/speech";
    const canonicalQuerystring = "";
    const contentType = "application/json";

    const bodyObj = {
        Text: text,
        OutputFormat: outputFormat,
        VoiceId: voiceId,
        Engine: "neural",
    };
    const requestBody = JSON.stringify(bodyObj);

    const now = new Date();
    const amzDate = toAmzDate(now);
    const dateStamp = toDateStamp(now);

    const signedHeaders = "content-type;host;x-amz-date";
    const canonicalHeaders =
        "content-type:" + contentType + "\n" +
        "host:" + host + "\n" +
        "x-amz-date:" + amzDate + "\n";

    const payloadHash = await sha256Hex(requestBody);

    const canonicalRequest =
        method + "\n" +
        canonicalUri + "\n" +
        canonicalQuerystring + "\n" +
        canonicalHeaders + "\n" +
        signedHeaders + "\n" +
        payloadHash;

    const algorithm = "AWS4-HMAC-SHA256";
    const credentialScope = `${dateStamp}/${region}/${service}/aws4_request`;
    const stringToSign =
        algorithm + "\n" +
        amzDate + "\n" +
        credentialScope + "\n" +
        await sha256Hex(canonicalRequest);

    const signingKey = await getSignatureKey(secretAccessKey, dateStamp, region, service);
    const signatureBytes = await hmacSha256(signingKey, stringToSign);
    const signature = toHex(signatureBytes);

    const authorizationHeader =
        `${algorithm} Credential=${accessKeyId}/${credentialScope}, ` +
        `SignedHeaders=${signedHeaders}, Signature=${signature}`;

    const headers = {
        "Content-Type": contentType,
        "X-Amz-Date": amzDate,
        "Authorization": authorizationHeader
    };

    const response = await fetch(endpoint + canonicalUri, {
        method: method,
        headers,
        body: requestBody
    });

    if (!response.ok) {
        const errText = await response.text();
        throw new Error(`Polly error ${response.status}: ${errText}`);
    }

    return await response.arrayBuffer();
}
