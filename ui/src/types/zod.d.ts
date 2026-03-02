declare module "zod" {
	export type ZodSchema<T = unknown> = {
		safeParse: (input: unknown) => { success: true; data: T } | { success: false };
	};

	type ZodNode<T = unknown> = ZodSchema<T> & {
		optional: () => ZodNode<T | undefined>;
		passthrough: () => ZodNode<T>;
	};

	export const z: {
		string: () => ZodNode<string>;
		number: () => ZodNode<number>;
		unknown: () => ZodNode<unknown>;
		literal: <T extends string>(value: T) => ZodNode<T>;
		object: <T extends Record<string, unknown>>(shape: T) => ZodNode<unknown>;
		array: <T>(item: ZodNode<T>) => ZodNode<T[]>;
		tuple: <T extends unknown[]>(items: { [K in keyof T]: ZodNode<T[K]> }) => ZodNode<T>;
		record: <T>(item: ZodNode<T>) => ZodNode<Record<string, T>>;
		infer: <T>(_schema: ZodSchema<T>) => T;
	};

	export type infer<T> = T extends ZodSchema<infer U> ? U : never;
}
